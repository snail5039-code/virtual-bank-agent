// 채팅 화면 : 입력을 서버(/api/chat)에 보내고 답을 대화에 붙입니다.
// 1단계 : 본인 확인을 묻는 중(pending = "secret")이면 입력칸을 비밀번호 칸으로 바꾸고, 대화에는 "****" 로만 남깁니다.
// 2단계 : 승인을 기다리면(pending = "approval") 글자 상자 대신 처리안 확인 카드를 그립니다.
//         버튼은 입력칸에 "승인" / "거절" 을 치는 것과 같습니다. 수정은 입력칸에 바꿀 내용을 적게 합니다.

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

async function submit(text, cardLabel) {
  if (busy) return;
  busy = true;
  add(input.type === "password" ? "****" : text, "me");
  closeCard(cardLabel || "수정 요청");
  input.value = "";
  input.placeholder = PLACEHOLDER;
  send.disabled = true;
  const waiting = add("에이전트가 작업 중입니다...", "notice");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    waiting.remove();
    for (const line of data.notices) add(line, "notice");
    if (data.proposal) addCard(data.proposal);
    else add(data.answer, "bot");
    input.type = data.pending === "secret" ? "password" : "text";
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
