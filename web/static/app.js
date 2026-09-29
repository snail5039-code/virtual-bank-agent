// 채팅 화면 : 입력을 서버(/api/chat)에 보내고 답을 대화에 붙입니다.
// 1단계 : 본인 확인을 묻는 중(pending = "secret")이면 입력칸을 비밀번호 칸으로 바꾸고, 대화에는 "****" 로만 남깁니다.
// 2단계 : 승인을 기다리면(pending = "approval") 글자 상자 대신 처리안 확인 카드를 그립니다.
//         버튼은 입력칸에 "승인" / "거절" 을 치는 것과 같습니다. 수정은 입력칸에 바꿀 내용을 적게 합니다.
// 3단계 : 옆 패널(총 잔액, 계좌, 카드, 카드값, 예약 이체, 최근 처리)을 /api/summary 로 채웁니다.
//         켤 때와 답을 받을 때마다 다시 읽습니다. 진행 상황은 멈춘 종류(pending)로 표시합니다.

// 로그인 (여러 사람용 2단계) : 로그인이 풀리면(서버를 다시 켰을 때 등) /api 가 401 을 돌려줍니다.
// 모든 fetch 를 한 곳에서 보고, 401 이면 로그인 화면으로 보냅니다.
const serverFetch = window.fetch;
window.fetch = async (...args) => {
  const res = await serverFetch(...args);
  if (res.status === 401) location.href = "/login";
  return res;
};

document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/login";
});

const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("text");
const send = document.getElementById("send");

// 처리안에서 크게 보여줄 금액 칸 이름 (업무마다 이름이 다릅니다)
const AMOUNT_LABELS = ["총액", "낼 금액", "합계", "입금액"];
const PLACEHOLDER = "요청을 입력하세요";

let openCard = null;    // 지금 답을 기다리는 처리안 카드
let busy = false;       // 서버가 처리 중이면 새 입력·버튼을 받지 않습니다 (두 번 보내지 않게)

function add(text, kind) {
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function drawProposal(body, proposal) {
  // 처리안 내용을 그립니다. 대화의 처리안 카드와 버튼 업무의 확인 창이 같이 씁니다.
  // 금액 칸은 크게, 주의 칸은 노란 안내로, 나머지는 이름 : 값 줄로 보여줍니다.
  body.appendChild(el("div", "task", proposal.task));
  const amount = proposal.rows.find(([label]) => AMOUNT_LABELS.includes(label));
  if (amount) {
    const big = el("div", "amount mono", amount[1].replace(/원$/, ""));
    if (amount[1].endsWith("원")) big.appendChild(el("small", "", "원"));
    body.appendChild(big);
  }
  for (const [label, value] of proposal.rows) {
    if (amount && label === amount[0]) continue;
    if (label === "주의") { body.appendChild(el("div", "warn", value)); continue; }
    const row = el("div", "row");
    row.appendChild(el("span", "", label));
    row.appendChild(el("span", /[0-9]/.test(value) ? "mono" : "", value));
    body.appendChild(row);
  }
}

function addCard(proposal) {
  const card = el("div", "card");
  const head = el("div", "card-head", "처리안 확인");
  const badge = el("span", "badge", "승인 대기");
  head.appendChild(badge);
  card.appendChild(head);

  const body = el("div", "card-body");
  drawProposal(body, proposal);
  if (proposal.retry) {
    body.appendChild(el("div", "warn", "답을 알아듣지 못했어요. 버튼을 누르거나 바꿀 내용을 적어 주세요."));
  }

  const actions = el("div", "actions");
  const ok = el("button", "primary", "승인");
  const edit = el("button", "ghost", "수정");
  const no = el("button", "ghost", "거절");
  ok.onclick = () => submit("승인", "승인함");
  no.onclick = () => submit("거절", "거절함");
  edit.onclick = () => {
    input.placeholder = "바꿀 내용을 입력하세요. 예: 5만원만";
    input.focus();
  };
  actions.append(ok, edit, no);
  body.appendChild(actions);
  card.appendChild(body);

  log.appendChild(card);
  log.scrollTop = log.scrollHeight;
  openCard = { badge, buttons: [ok, edit, no] };
}

function closeCard(label) {
  // 답을 보낸 카드는 버튼을 막고, 사용자가 무엇을 했는지 표시합니다. (결과는 아래 에이전트 답에 나옵니다)
  if (!openCard) return;
  openCard.badge.textContent = label;
  openCard.badge.className = "badge done-badge";
  openCard.buttons.forEach((b) => (b.disabled = true));
  openCard = null;
}

// ---------------------------------------------------------------- 옆 패널 (3단계)
const won = (n) => n.toLocaleString("ko-KR");
const CARD_BADGE = { active: "b-ok", locked: "b-warn", lost: "b-bad" };
const REQUEST_BADGE = { "완료": "b-ok", "실패": "b-bad" };     // 그 밖(거절·취소)은 옅은 회색

// 진행 상황 : 변경 업무의 순서입니다. 멈춘 종류로 지금 어디인지 정합니다.
const STEPS = ["요청 이해", "검사", "본인 확인", "승인 대기", "실행과 저장"];
const NOW_STEP = { question: 0, secret: 2, approval: 3 };

function line(name, right) {
  const div = el("div", "line");
  div.appendChild(el("span", "", name));
  div.appendChild(right);
  return div;
}

function fill(id, nodes, emptyText) {
  const box = document.getElementById(id);
  box.replaceChildren(...(nodes.length ? nodes : [el("div", "empty", emptyText)]));
}

function shortTime(iso) {
  // "2026-09-30T09:00:00" → "09-30 09:00"
  return iso.slice(5, 10) + " " + iso.slice(11, 16);
}

async function loadSummary() {
  const s = await (await fetch("/api/summary")).json();
  document.getElementById("user").textContent = s.user;
  document.getElementById("auth").textContent = s.authenticated ? "본인 확인 완료" : "본인 확인 전";
  document.getElementById("total").textContent = won(s.total);

  fill("accounts", s.accounts.map((a) => {
    const box = el("div", "acc");
    box.append(el("div", "", a.name), el("div", "mono", won(a.balance)));
    return box;
  }), "계좌가 없어요");
  fill("cards", s.cards.map((c) => line(c.name, el("span", "badge " + (CARD_BADGE[c.status] || "b-plain"), c.label))), "카드가 없어요");
  fill("bills", s.bills.count ? [line("낼 돈이 남은 청구서 " + s.bills.count + "건", el("span", "mono", won(s.bills.amount) + "원"))] : [], "낼 카드값이 없어요");
  fill("schedules", s.schedules.map((x) => line(shortTime(x.at) + "  " + x.to, el("span", "mono", won(x.amount) + "원"))), "걸어 둔 예약이 없어요");
  fill("requests", s.requests.map((r) => line(r.task, el("span", "badge " + (REQUEST_BADGE[r.status] || "b-plain"), r.status))), "아직 처리한 업무가 없어요");
}

function showSteps(pending) {
  const now = NOW_STEP[pending];
  if (now === undefined) {
    fill("steps", [], "진행 중인 업무가 없어요");
    return;
  }
  fill("steps", STEPS.map((name, i) => {
    if (i < now) return el("div", "", "✓ " + name);
    if (i === now) return el("div", "now", "‖ " + name + (pending === "question" ? " (질문에 답해 주세요)" : ""));
    return el("div", "todo", "○ " + name);
  }));
}

function showAlerts(lines) {
  // 예약 이체·분할 회차가 실행된 결과를 오른쪽 알림에 쌓습니다. (최근 것이 위, 5개까지)
  if (!lines.length) return;
  const box = document.getElementById("alerts");
  for (const text of lines) box.prepend(el("div", "alert", text));
  while (box.children.length > 5) box.lastChild.remove();
  document.getElementById("alerts-box").hidden = false;
}

// ---------------------------------------------------------------- 보내기
let busyNote = null;    // 처리 중에 또 보내려고 할 때 띄우는 안내 (하나만)

async function submit(text, cardLabel) {
  if (busy) {
    // 보내지 않고 입력은 입력칸에 그대로 둡니다. 답이 오면 안내를 지웁니다.
    if (!busyNote) busyNote = add("에이전트가 답하는 중이에요. 답이 오면 다시 보내 주세요. (입력한 내용은 그대로 있어요)", "notice");
    return;
  }
  add(input.type === "password" ? "****" : text, "me");
  closeCard(cardLabel || "수정 요청");
  await call("/api/chat", { text });
}

async function call(url, payload) {
  // 서버에 보내고, 돌아온 답(answer / pending / proposal / notices)을 화면에 붙입니다.
  // 채팅과 재시작 복구가 같이 씁니다.
  busy = true;
  input.value = "";
  input.placeholder = PLACEHOLDER;
  // 보내기 버튼은 흐리게만 합니다. disabled 로 막으면 Enter 가 아예 안 먹어서 "답하는 중" 안내도 못 띄웁니다.
  send.classList.add("waiting");
  const waiting = add("에이전트가 작업 중입니다...", "notice");

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    waiting.remove();
    for (const text of data.notices) add(text, "notice");
    showAlerts(data.notices);
    showReply(data);
    await loadSummary();
  } catch (e) {
    waiting.remove();
    add("서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.", "notice");
  }
  busy = false;
  if (busyNote) { busyNote.remove(); busyNote = null; }
  send.classList.remove("waiting");
  input.focus();
}

function showReply(data) {
  // 답(또는 멈춘 질문·처리안)을 대화에 붙이고, 입력칸과 진행 상황을 멈춘 종류에 맞춥니다.
  if (data.proposal) addCard(data.proposal);
  else add(data.answer, "bot");
  const type = data.pending === "secret" ? "password" : "text";
  // 입력칸 종류가 바뀌면(보통 칸 ↔ 비밀번호 칸) 기다리는 동안 쳐 둔 글자를 지웁니다.
  // 그대로 두면 다른 요청으로 쓴 글이 비밀번호 답으로 들어갈 수 있습니다.
  if (input.type !== type) input.value = "";
  input.type = type;
  lastPending = data.pending;
  showSteps(data.pending);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (text) submit(text);
});

// ---------------------------------------------------------------- 빠른 실행
let lastPending = null;     // 지금 에이전트가 멈춰 있는 종류 (question / secret / approval / null)

document.querySelectorAll(".quick button").forEach((button) => {
  // 빠른 실행도 버튼 업무입니다. 이체는 이체 창을, 나머지는 대상을 고르는 창을 엽니다.
  button.addEventListener("click", () => quickAction(button.dataset.open));
});

// ---------------------------------------------------------------- 메뉴 화면
// 메뉴는 화면을 바꿉니다. 에이전트 = 대화, 나머지 = /api/view/<이름> 을 바로 읽어 표로 보여줍니다. (LLM 없음)
// 표의 버튼(잠그기, 내기, 취소 …)은 바꾸는 일이라 에이전트 입력칸에 요청을 채우기만 합니다. (본인 확인 → 처리안 → 승인)

const agentView = document.getElementById("agent-view");
const pageView = document.getElementById("page-view");
const pageTitle = document.getElementById("page-title");
const pageTools = document.getElementById("page-tools");
const pageBody = document.getElementById("page-body");
let currentView = "agent";

function showView(name) {
  currentView = name;
  document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("on", n.dataset.view === name));
  agentView.hidden = name !== "agent";
  pageView.hidden = name === "agent";
  if (name !== "agent") renderPage(name);
}

document.querySelectorAll(".nav").forEach((nav) => {
  nav.addEventListener("click", () => showView(nav.dataset.view));
});

function table(headers, rows) {
  // headers : [["제목", "num"(오른쪽 정렬) 또는 ""], …]  rows : [[칸, …], …] (칸은 글자 또는 요소)
  const t = el("table");
  const head = el("tr");
  for (const [text, cls] of headers) head.appendChild(el("th", cls, text));
  t.appendChild(head);
  for (const row of rows) {
    const tr = el("tr");
    row.forEach((cell, i) => {
      const td = el("td", headers[i][1]);
      if (cell instanceof Node) td.appendChild(cell);
      else td.textContent = cell ?? "";
      tr.appendChild(td);
    });
    t.appendChild(tr);
  }
  return t;
}

// ---------------------------------------------------------------- 버튼 업무 확인 창
// 표의 버튼으로 바로 하는 업무입니다 (LLM 없음). 서버가 먼저 검사하고 처리안을 주면 확인 창으로 보여주고,
// 승인하면 본인 확인(아직이면) → 다시 검사 → 실행 → 처리 기록 → 저장 순서로 서버가 처리합니다.
const modal = document.getElementById("modal");
const modalBody = document.getElementById("modal-body");

function closeModal() { modal.hidden = true; modalBody.replaceChildren(); }

async function postJSON(url, payload) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return res.json();
}

function modalMessage(text, cls) {
  // 확인 창 안에 결과·사유를 보여주고 닫기 버튼만 남깁니다.
  modalBody.replaceChildren(el("div", "modal-msg " + (cls || ""), text));
  const close = el("button", "primary", "닫기");
  close.onclick = closeModal;
  const actionsRow = el("div", "actions");
  actionsRow.appendChild(close);
  modalBody.appendChild(actionsRow);
  close.focus();
}

async function openAction(kind, target, params = {}) {
  if (busy) return;
  modal.hidden = false;
  modalBody.replaceChildren(el("div", "empty", "확인하는 중..."));
  const pre = await postJSON("/api/action/preview", { kind, target, params });
  if (pre.error) { modalMessage(pre.error, "bad"); return; }
  showConfirm(kind, target, params, pre);
}

function showConfirm(kind, target, params, pre) {
  // 처리안 + (본인 확인 칸) + 승인 / 거절. 승인하면 서버가 다시 검사한 뒤 실행합니다.
  modalBody.replaceChildren();
  const head = el("div", "modal-head", "처리안 확인");
  modalBody.appendChild(head);
  drawProposal(modalBody, pre.proposal);

  let secretInput = null;
  const authError = el("div", "auth-error");
  if (pre.need_auth) {
    modalBody.appendChild(el("div", "auth-label", "본인 확인 : 계좌 비밀번호, PIN, 휴대전화번호, 주민번호 뒷자리 중 하나"));
    secretInput = el("input");
    secretInput.type = "password";
    secretInput.autocomplete = "off";
    modalBody.append(secretInput, authError);
  }

  const actionsRow = el("div", "actions");
  const ok = el("button", "primary", "승인");
  const no = el("button", "ghost", "거절");
  actionsRow.append(ok, no);
  modalBody.appendChild(actionsRow);
  (secretInput || ok).focus();

  const run = async (approve) => {
    ok.disabled = no.disabled = true;
    const res = await postJSON("/api/action/run", { kind, target, params, approve, secret: secretInput ? secretInput.value : null });
    if (res.auth_error) {            // 본인 확인이 틀림 : 창은 그대로 두고 다시 입력받습니다
      authError.textContent = res.auth_error;
      secretInput.value = "";
      secretInput.focus();
      ok.disabled = no.disabled = false;
      return;
    }
    if (res.error) modalMessage(res.error, "bad");
    else modalMessage(res.answer, res.result === "완료" ? "ok" : "");
    await loadSummary();
    if (currentView !== "agent") renderPage(currentView);
  };
  ok.onclick = () => run(true);
  no.onclick = () => run(false);
  if (secretInput) secretInput.onkeydown = (e) => { if (e.key === "Enter") run(true); };
}

// 이체 창 : 출금 · 입금 · 금액 · (예약 시각). 다음을 누르면 서버가 검사하고, 되면 처리안 확인으로 넘어갑니다.
//   options.from     : 미리 골라 둘 출금 계좌 ID (계좌 화면의 이체 버튼)
//   options.schedule : 예약 시각 칸을 켠 채로 엽니다 (예약 이체 화면의 버튼)
async function openTransfer(options = {}) {
  if (busy) return;
  modal.hidden = false;
  modalBody.replaceChildren(el("div", "empty", "불러오는 중..."));
  const opt = await (await fetch("/api/view/transfer_options")).json();

  const field = (label, control) => {
    const box = el("label", "field");
    box.append(el("span", "", label), control);
    return box;
  };
  const fromSel = el("select");
  for (const a of opt.accounts) fromSel.appendChild(new Option(a.name + "  (잔액 " + won(a.balance) + "원)", a.id));
  if (options.from) fromSel.value = options.from;
  const toSel = el("select");
  toSel.appendChild(new Option("입금 계좌를 고르세요", ""));
  for (const t of opt.targets) toSel.appendChild(new Option(t.name, t.id));
  const amount = el("input");
  amount.inputMode = "numeric";
  amount.placeholder = "예: 100000";

  const useTime = el("input");
  useTime.type = "checkbox";
  useTime.checked = !!options.schedule;
  const at = el("input");
  at.type = "datetime-local";
  // 기본값 : 내일 09:00 (이 컴퓨터 날짜 기준. toISOString 은 UTC 라 새벽에는 날짜가 하루 어긋납니다)
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n) => String(n).padStart(2, "0");
  at.value = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T09:00";
  const timeRow = field("예약 시각", at);
  timeRow.hidden = !useTime.checked;
  const head = el("div", "modal-head", useTime.checked ? "예약 이체" : "이체");
  useTime.onchange = () => {
    timeRow.hidden = !useTime.checked;
    head.textContent = useTime.checked ? "예약 이체" : "이체";
  };
  const timeToggle = el("label", "check");
  timeToggle.append(useTime, el("span", "", "예약 이체로 보내기"));

  const formError = el("div", "auth-error");
  const next = el("button", "primary", "다음");
  const cancel = el("button", "ghost", "닫기");
  cancel.onclick = closeModal;
  const actionsRow = el("div", "actions");
  actionsRow.append(next, cancel);

  modalBody.replaceChildren(head,
    field("출금 계좌", fromSel), field("입금 계좌", toSel), field("금액 (원)", amount),
    timeToggle, timeRow, formError, actionsRow);
  (options.from ? toSel : fromSel).focus();

  next.onclick = async () => {
    const params = { from: fromSel.value, to: toSel.value, amount: amount.value, at: useTime.checked ? at.value : "" };
    next.disabled = true;
    const pre = await postJSON("/api/action/preview", { kind: "transfer", target: "", params });
    next.disabled = false;
    if (pre.error) { formError.textContent = pre.error; return; }     // 창은 그대로 두고 고치게 합니다
    showConfirm("transfer", "", params, pre);
  };
  amount.onkeydown = (e) => { if (e.key === "Enter") next.click(); };
}

// 재발급 창 : 배송지(집 / 회사)를 고르고 다음을 누르면 서버가 검사하고, 되면 처리안 확인으로 넘어갑니다.
async function openReissue(card) {
  if (busy) return;
  modal.hidden = false;
  modalBody.replaceChildren(el("div", "empty", "불러오는 중..."));
  const addresses = await (await fetch("/api/view/addresses")).json();

  const choice = el("div", "choices");
  let picked = null;
  for (const a of addresses) {
    const option = el("label", "check");
    const radio = el("input");
    radio.type = "radio";
    radio.name = "address";
    radio.onchange = () => { picked = a.id; };
    option.append(radio, el("span", "", a.label + "  " + a.address));
    choice.appendChild(option);
  }
  const formError = el("div", "auth-error");
  const next = el("button", "primary", "다음");
  const cancel = el("button", "ghost", "닫기");
  cancel.onclick = closeModal;
  const actionsRow = el("div", "actions");
  actionsRow.append(next, cancel);
  modalBody.replaceChildren(el("div", "modal-head", "카드 재발급"),
    el("div", "task", "새 카드를 받을 배송지를 골라 주세요. (" + card.name + ")"), choice, formError, actionsRow);

  next.onclick = async () => {
    const params = { address: picked };
    next.disabled = true;
    const pre = await postJSON("/api/action/preview", { kind: "reissue", target: card.id, params });
    next.disabled = false;
    if (pre.error) { formError.textContent = pre.error; return; }
    showConfirm("reissue", card.id, params, pre);
  };
}

// 입력 창 (등록처럼 칸만 채우면 되는 업무) : 칸을 채우고 다음을 누르면 서버가 검사하고, 되면 처리안 확인으로 넘어갑니다.
//   fields : [{key, label, placeholder, optional, options:[[값, 보이는 글], …] (있으면 고르기)}]
const ACCOUNT_FORM = {
  title: "상대 계좌 등록", kind: "account_register",
  fields: [
    { key: "bank_name", label: "은행", banks: true },
    { key: "account_number", label: "계좌번호 (은행마다 자릿수가 달라요)", bankExample: true },
    { key: "holder_name", label: "예금주", placeholder: "예: 이영희" },
    { key: "nickname", label: "별명 (안 쓰면 예금주 이름)", placeholder: "예: 친구 영희", optional: true },
  ],
};
const OPEN_FORM = {
  title: "내 계좌 만들기", kind: "account_open",
  fields: [
    { key: "bank_name", label: "은행", banks: true },
    { key: "account_number", label: "계좌번호 (직접 정해요. 은행마다 자릿수가 달라요)", bankExample: true },
    { key: "nickname", label: "별명", placeholder: "예: 비상금" },
    { key: "purpose", label: "용도 (선택)", placeholder: "예: 급할 때 쓰는 돈", optional: true },
    { key: "password", label: "계좌 비밀번호 (숫자 4자리)", secret: true },
  ],
};
const CARD_FORM = {
  title: "카드 등록", kind: "card_register",
  fields: [
    { key: "bank_name", label: "은행", banks: true },
    { key: "card_number", label: "카드 번호 (16자리)", placeholder: "예: 1234-5678-1234-5678" },
    { key: "card_type", label: "종류", options: [["체크", "체크카드"], ["신용", "신용카드"]] },
    { key: "account_id", label: "결제 계좌", options: [] },
    { key: "name", label: "별칭 (안 쓰면 은행 + 종류)", placeholder: "예: 장보기 카드", optional: true },
  ],
};
const DEPOSIT_FORM = {
  title: "가상 입금", kind: "deposit",
  fields: [
    { key: "account", label: "입금할 내 계좌", options: [] },
    { key: "amount", label: "금액 (한 번에 1,000만원까지)", placeholder: "예: 100000" },
  ],
};

async function openForm(form) {
  if (busy) return;
  // 은행 칸(banks: true)은 서버의 은행 목록(/api/view/banks)으로 고르기를 만듭니다.
  const banks = form.fields.some((f) => f.banks) ? await (await fetch("/api/view/banks")).json() : [];
  modal.hidden = false;
  const inputs = {};
  const parts = [el("div", "modal-head", form.title)];
  for (const f of form.fields) {
    let control;
    if (f.banks) {
      control = el("select");
      for (const b of banks) control.appendChild(new Option(b.name, b.name));
    } else if (f.options) {
      control = el("select");
      for (const [value, text] of f.options) control.appendChild(new Option(text, value));
    } else {
      control = el("input");
      control.placeholder = f.placeholder || "";
      control.autocomplete = "off";
      if (f.secret) control.type = "password";      // 비밀번호 칸은 가립니다
    }
    inputs[f.key] = control;
    const box = el("label", "field");
    box.append(el("span", "", f.label), control);
    parts.push(box);
  }
  const formError = el("div", "auth-error");
  const next = el("button", "primary", "다음");
  const cancel = el("button", "ghost", "닫기");
  cancel.onclick = closeModal;
  const actionsRow = el("div", "actions");
  actionsRow.append(next, cancel);
  modalBody.replaceChildren(...parts, formError, actionsRow);
  inputs[form.fields[0].key].focus();

  // 계좌번호 칸(bankExample)은 고른 은행의 계좌번호 모양을 예시로 보여줍니다. 숫자만 적어도 서버가 모양에 맞춰 줍니다.
  const numberField = form.fields.find((f) => f.bankExample);
  if (numberField && inputs.bank_name) {
    const showExample = () => {
      const bank = banks.find((b) => b.name === inputs.bank_name.value);
      inputs[numberField.key].placeholder = bank ? "예: " + bank.example : "";
    };
    inputs.bank_name.addEventListener("change", showExample);
    showExample();
  }

  next.onclick = async () => {
    const params = Object.fromEntries(Object.entries(inputs).map(([k, c]) => [k, c.value]));
    next.disabled = true;
    const target = form.target || "";       // 해지처럼 대상이 정해진 창이면 그 ID
    const pre = await postJSON("/api/action/preview", { kind: form.kind, target, params });
    next.disabled = false;
    if (pre.error) { formError.textContent = pre.error; return; }     // 창은 그대로 두고 고치게 합니다
    showConfirm(form.kind, target, params, pre);
  };
}

function button(label, onClick) {
  const b = el("button", "act", label);
  b.onclick = onClick;
  return b;
}

function badge(text, cls) { return el("span", "badge " + cls, text); }

function accountButtons(a) {
  // 내 계좌 한 줄의 버튼 : 이체, 정지 / 정지 풀기, 해지 (할 수 있는지는 서버가 검사합니다)
  const box = el("span", "btns");
  box.append(button("이체", () => openTransfer({ from: a.id })));
  box.append(a.status === "suspended" ? button("정지 풀기", () => openAction("account_resume", a.id))
                                      : button("정지", () => openAction("account_suspend", a.id)));
  box.append(button("해지", () => closeAccount(a)));
  return box;
}

function accountName(a) {
  // 정지된 계좌는 이름 옆에 "정지" 표시를 붙입니다.
  if (a.status !== "suspended") return a.name;
  const box = el("span", "", a.name + " ");
  box.appendChild(badge("정지", "b-bad"));
  return box;
}

async function closeAccount(a) {
  // 잔액이 없으면 바로 확인으로, 남아 있으면 먼저 남은 돈을 받을 계좌(내 다른 계좌 / 등록 계좌)를 고르게 합니다.
  if (a.balance <= 0) { openAction("account_close", a.id); return; }
  const opt = await (await fetch("/api/view/transfer_options")).json();
  openForm({
    title: "계좌 해지", kind: "account_close", target: a.id,
    fields: [{ key: "to", label: "남은 돈 " + won(a.balance) + "원을 받을 계좌",
               options: opt.targets.filter((t) => t.id !== a.id).map((t) => [t.id, t.name]) }],
  });
}

function cardButtons(c) {
  // 카드 상태에 따라 할 수 있는 버튼 : 사용 가능 → 잠그기, 잠금 → 잠금 풀기, 분실 정지 → 재발급. 해지 전이면 해지도.
  if (c.status === "cancelled") return "";
  const box = el("span", "btns");
  if (c.status === "active") box.appendChild(button("잠그기", () => openAction("card_lock", c.id)));
  if (c.status === "locked") box.appendChild(button("잠금 풀기", () => openAction("card_unlock", c.id)));
  if (c.status === "lost") box.appendChild(button("재발급", () => openReissue(c)));
  box.appendChild(button("해지", () => openAction("card_cancel", c.id)));
  return box;
}

// 고르기 창 : 위쪽 빠른 실행(카드 잠금, 카드값 내기, 재발급)에서 대상을 먼저 고르게 합니다.
//   items : [{label, sub, pick}]  pick 을 누르면 그 대상의 버튼 업무로 넘어갑니다
function openPicker(title, items, emptyText) {
  if (busy) return;
  modal.hidden = false;
  const list = el("div", "pick-list");
  for (const item of items) {
    const row = el("button", "pick");
    row.append(el("span", "", item.label), el("span", "sub", item.sub || ""));
    row.onclick = item.pick;
    list.appendChild(row);
  }
  const cancel = el("button", "ghost", "닫기");
  cancel.onclick = closeModal;
  const actionsRow = el("div", "actions");
  actionsRow.appendChild(cancel);
  modalBody.replaceChildren(el("div", "modal-head", title), items.length ? list : el("div", "empty", emptyText), actionsRow);
}

async function quickAction(kind) {
  if (kind === "transfer") { openTransfer(); return; }
  if (kind === "deposit") {
    const opt = await (await fetch("/api/view/transfer_options")).json();     // 내 계좌
    if (!opt.accounts.length) { openPicker("가상 입금", [], "계좌가 없어요. 계좌 화면에서 '내 계좌 만들기' 를 먼저 해 주세요"); return; }
    openForm({ ...DEPOSIT_FORM, fields: DEPOSIT_FORM.fields.map((f) => f.key === "account"
      ? { ...f, options: opt.accounts.map((a) => [a.id, a.name + "  (잔액 " + won(a.balance) + "원)"]) } : f) });
    return;
  }
  if (kind === "bill") {
    const bills = (await (await fetch("/api/view/bills")).json()).filter((s) => s.remaining > 0);
    openPicker("어떤 카드값을 낼까요?", bills.map((s) => ({
      label: s.card + " " + s.month, sub: won(s.remaining) + "원  기한 " + s.due,
      pick: () => openAction("bill_pay", s.id),
    })), "낼 카드값이 없어요");
    return;
  }
  const cards = await (await fetch("/api/view/cards")).json();
  if (kind === "lock") {
    openPicker("어떤 카드를 잠글까요?", cards.filter((c) => c.status === "active").map((c) => ({
      label: c.name, sub: c.type + " / " + c.account, pick: () => openAction("card_lock", c.id),
    })), "잠글 수 있는 카드가 없어요");
  }
  if (kind === "reissue") {
    openPicker("어떤 카드를 재발급할까요? (분실 정지 카드)", cards.filter((c) => c.status === "lost").map((c) => ({
      label: c.name, sub: c.type + " / " + c.account, pick: () => openReissue(c),
    })), "분실 정지된 카드가 없어요. 먼저 분실 신고를 해 주세요");
  }
}
function stamp(iso) { return iso.slice(0, 10) + " " + iso.slice(11, 16); }     // "2026-09-30 09:00"

const PAGES = {
  accounts: {
    title: "계좌",
    also: "registered",     // 아래에 등록 계좌(상대 계좌)도 같이 보여줍니다
    tools: () => [button("내 계좌 만들기", () => openForm(OPEN_FORM)), button("상대 계좌 등록", () => openForm(ACCOUNT_FORM)),
                  button("가상 입금", () => quickAction("deposit"))],
    draw: (rows, registered) => {
      const box = el("div");
      box.appendChild(table(
        [["계좌", ""], ["은행 / 계좌번호", ""], ["용도", ""], ["잔액", "num"], ["", "num"]],
        rows.map((a) => [accountName(a),
                         a.bank + " " + a.number, a.purpose, el("span", "mono", won(a.balance) + "원"),
                         accountButtons(a)])));
      box.appendChild(el("h3", "sub-title", "등록 계좌"));
      box.appendChild(registered.length ? table(
        [["별명", ""], ["은행 / 계좌번호", ""], ["예금주", ""], ["", "num"]],
        registered.map((r) => [r.name, r.bank + " " + r.number, r.holder,
                               button("삭제", () => openAction("registered_delete", r.id))])) : el("div", "empty", "등록한 상대 계좌가 없어요"));
      return box;
    },
  },
  transactions: {
    title: "거래 내역",
    tools: (rows, redraw) => {
      // 계좌·입출금 고르기 : 화면 안에서만 거릅니다 (서버에 다시 묻지 않음)
      const accountSel = el("select");
      accountSel.append(new Option("모든 계좌", ""), ...[...new Set(rows.map((r) => r.account))].map((n) => new Option(n, n)));
      const typeSel = el("select");
      typeSel.append(new Option("입금·출금", ""), new Option("입금", "입금"), new Option("출금", "출금"));
      const apply = () => redraw(rows.filter((r) => (!accountSel.value || r.account === accountSel.value)
                                                 && (!typeSel.value || r.type === typeSel.value)));
      accountSel.onchange = apply;
      typeSel.onchange = apply;
      return [accountSel, typeSel];
    },
    draw: (rows) => table(
      [["날짜", ""], ["계좌", ""], ["내용", ""], ["금액", "num"]],
      rows.map((t) => [el("span", "mono", stamp(t.at)), t.account,
                       [t.merchant, t.card && "(" + t.card + ")"].filter(Boolean).join(" ") || t.type,
                       el("span", "mono", (t.type === "출금" ? "- " : "+ ") + won(t.amount) + "원")])),
  },
  cards: {
    title: "카드",
    tools: () => [button("카드 등록", async () => {
      const opt = await (await fetch("/api/view/transfer_options")).json();     // 결제 계좌 = 내 계좌
      openForm({ ...CARD_FORM, fields: CARD_FORM.fields.map((f) => f.key === "account_id"
        ? { ...f, options: opt.accounts.map((a) => [a.id, a.name]) } : f) });
    })],
    draw: (rows) => table(
      [["카드", ""], ["종류", ""], ["연결 계좌", ""], ["상태", ""], ["", "num"]],
      rows.map((c) => [c.name, c.type + (c.bank ? " / " + c.bank : ""), c.account,
                       badge(c.label, CARD_BADGE[c.status] || "b-plain"),
                       cardButtons(c)])),
  },
  bills: {
    title: "카드값",
    draw: (rows) => table(
      [["카드", ""], ["청구 월", ""], ["청구액", "num"], ["남은 금액", "num"], ["기한", ""], ["상태", ""], ["", "num"]],
      rows.map((s) => [s.card, s.month, el("span", "mono", won(s.total)), el("span", "mono", won(s.remaining)),
                       el("span", "mono", s.due), badge(s.label, s.status === "paid" ? "b-ok" : s.status === "partial" ? "b-warn" : "b-bad"),
                       s.remaining > 0 ? button("전체 내기", () => openAction("bill_pay", s.id)) : ""])),
  },
  schedules: {
    title: "예약 이체",
    tools: () => [button("예약 이체 하기", () => openTransfer({ schedule: true }))],
    draw: (rows) => table(
      [["예약 시각", ""], ["출금 → 입금", ""], ["금액", "num"], ["상태", ""], ["", "num"]],
      rows.map((s) => [el("span", "mono", stamp(s.at)), s.from + " → " + s.to, el("span", "mono", won(s.amount) + "원"),
                       badge(s.status, s.status === "완료" ? "b-ok" : s.status === "실패" ? "b-bad" : s.status === "예약" ? "b-warn" : "b-plain"),
                       s.status === "예약" ? button("취소", () => openAction("schedule_cancel", s.id)) : ""])),
  },
  requests: {
    title: "처리 기록",
    draw: (rows) => table(
      [["시각", ""], ["업무", ""], ["내용", ""], ["결과", ""]],
      rows.map((r) => [el("span", "mono", stamp(r.at)), r.task,
                       el("div", "content", Object.entries(r.content || {}).map(([k, v]) => k + " : " + v).join("\n")),
                       badge(r.status, REQUEST_BADGE[r.status] || "b-plain")])),
  },
};

const EMPTY = { accounts: "계좌가 없어요", transactions: "거래 내역이 없어요", cards: "카드가 없어요",
                bills: "청구서가 없어요", schedules: "걸어 둔 예약이 없어요", requests: "아직 처리한 업무가 없어요" };

async function renderPage(name) {
  const page = PAGES[name];
  pageTitle.textContent = page.title;
  pageTools.replaceChildren();
  pageBody.replaceChildren(el("div", "empty", "불러오는 중..."));
  const rows = await (await fetch("/api/view/" + name)).json();
  const also = page.also ? await (await fetch("/api/view/" + page.also)).json() : null;
  if (currentView !== name) return;       // 불러오는 사이에 다른 메뉴로 갔으면 그리지 않습니다
  const redraw = (list) => pageBody.replaceChildren(list.length ? page.draw(list, also) : el("div", "empty", EMPTY[name]));
  if (page.tools) pageTools.replaceChildren(...page.tools(rows, redraw));
  redraw(rows);
}

// ---------------------------------------------------------------- 스케줄러 알림 (4단계)
// 서버의 30초 스케줄러가 입력 없이 실행한 결과를 10초마다 가져옵니다. 있으면 대화·알림에 붙이고 패널을 다시 읽습니다.
setInterval(async () => {
  try {
    const { alerts } = await (await fetch("/api/alerts")).json();
    if (!alerts.length) return;
    for (const text of alerts) add(text, "notice");
    showAlerts(alerts);
    await loadSummary();
    if (currentView !== "agent") renderPage(currentView);   // 보고 있던 메뉴 화면도 새 값으로
  } catch (e) { /* 서버가 꺼져 있으면 다음에 다시 봅니다 */ }
}, 10000);

// ---------------------------------------------------------------- 재시작 복구 (4단계)
// 서버를 켤 때 끝나지 않은 업무가 남아 있었으면 먼저 묻습니다. 다시 하면 처음부터 (승인도 다시).
async function checkRecovery() {
  const { record } = await (await fetch("/api/recovery")).json();
  if (!record) return;

  const card = el("div", "card");
  const head = el("div", "card-head", "진행 중이던 업무");
  const badge = el("span", "badge b-warn", record.kind);
  head.appendChild(badge);
  const body = el("div", "card-body");
  body.appendChild(el("div", "task", record.when + " 요청이 끝나기 전에 종료되었어요."));
  body.appendChild(el("div", "amount", record.request_text));
  body.appendChild(el("div", "warn", "처음부터 다시 진행하면 잔액과 카드 상태를 다시 확인하고, 승인도 다시 받아요."));
  const actions = el("div", "actions");
  const again = el("button", "primary", "처음부터 다시");
  const drop = el("button", "ghost", "지우기");
  actions.append(again, drop);
  body.appendChild(actions);
  card.append(head, body);
  log.appendChild(card);

  const choose = (yes) => {
    if (busy) return;
    [again, drop].forEach((b) => (b.disabled = true));
    badge.textContent = yes ? "다시 진행" : "지움";
    badge.className = "badge b-plain";
    add(yes ? "처음부터 다시" : "지우기", "me");
    call("/api/recovery", { again: yes });
  };
  again.onclick = () => choose(true);
  drop.onclick = () => choose(false);
}

// ---------------------------------------------------------------- 새로고침 뒤 이어서 보기
// 업무 중간에 새로고침해도 서버의 그래프는 멈춘 채로 있습니다. 멈춘 질문이나 처리안을 다시 그려서
// 다음 입력이 무엇의 답으로 들어가는지 보이게 합니다.
async function restoreWaiting() {
  const data = await (await fetch("/api/waiting")).json();
  if (!data.pending) return;
  add("새로고침 전에 진행하던 업무예요. 이어서 답해 주세요.", "notice");
  showReply(data);
}

loadSummary();
checkRecovery();
restoreWaiting();
