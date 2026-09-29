// 채팅 화면 : 입력을 서버(/api/chat)에 보내고 답을 대화에 붙입니다.
// 1단계 : 본인 확인을 묻는 중(pending = "secret")이면 입력칸을 비밀번호 칸으로 바꾸고, 대화에는 "****" 로만 남깁니다.
// 2단계 : 승인을 기다리면(pending = "approval") 글자 상자 대신 처리안 확인 카드를 그립니다.
//         버튼은 입력칸에 "승인" / "거절" 을 치는 것과 같습니다. 수정은 입력칸에 바꿀 내용을 적게 합니다.
// 3단계 : 옆 패널(총 잔액, 계좌, 카드, 카드값, 예약 이체, 최근 처리)을 /api/summary 로 채웁니다.
//         켤 때와 답을 받을 때마다 다시 읽습니다. 진행 상황은 멈춘 종류(pending)로 표시합니다.

const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("text");
const send = document.getElementById("send");

// 처리안에서 크게 보여줄 금액 칸 이름 (업무마다 이름이 다릅니다)
const AMOUNT_LABELS = ["총액", "낼 금액", "합계"];
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

function addCard(proposal) {
  const card = el("div", "card");
  const head = el("div", "card-head", "처리안 확인");
  const badge = el("span", "badge", "승인 대기");
  head.appendChild(badge);
  card.appendChild(head);

  const body = el("div", "card-body");
  body.appendChild(el("div", "task", proposal.task));

  // 금액 칸은 크게, 주의 칸은 노란 안내로, 나머지는 이름 : 값 줄로 보여줍니다.
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
async function submit(text, cardLabel) {
  if (busy) return;
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
  send.disabled = true;
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
    if (data.proposal) addCard(data.proposal);
    else add(data.answer, "bot");
    input.type = data.pending === "secret" ? "password" : "text";
    lastPending = data.pending;
    showSteps(data.pending);
    await loadSummary();
  } catch (e) {
    waiting.remove();
    add("서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.", "notice");
  }
  busy = false;
  send.disabled = false;
  input.focus();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (text) submit(text);
});

// ---------------------------------------------------------------- 메뉴 · 빠른 실행 (4단계)
let lastPending = null;     // 지금 멈춰 있는 종류. 멈춘 동안에는 메뉴가 요청을 바로 보내지 않습니다.

function fillInput(text) {
  input.value = text;
  input.focus();
}

document.querySelectorAll(".nav").forEach((nav) => {
  nav.addEventListener("click", () => {
    document.querySelectorAll(".nav").forEach((n) => n.classList.remove("on"));
    nav.classList.add("on");
    const text = nav.dataset.ask;
    if (!text) { input.focus(); return; }
    // 질문·승인을 기다리는 중에 새 요청을 바로 보내면 지금 업무가 "다른 요청" 으로 멈춥니다.
    // 그래서 그때는 입력칸에만 채우고, 사용자가 직접 보내게 합니다.
    if (lastPending || busy) fillInput(text);
    else submit(text);
  });
});

document.querySelectorAll(".quick button").forEach((button) => {
  button.addEventListener("click", () => fillInput(button.dataset.fill));
});

// ---------------------------------------------------------------- 스케줄러 알림 (4단계)
// 서버의 30초 스케줄러가 입력 없이 실행한 결과를 10초마다 가져옵니다. 있으면 대화·알림에 붙이고 패널을 다시 읽습니다.
setInterval(async () => {
  try {
    const { alerts } = await (await fetch("/api/alerts")).json();
    if (!alerts.length) return;
    for (const text of alerts) add(text, "notice");
    showAlerts(alerts);
    await loadSummary();
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

loadSummary();
checkRecovery();
