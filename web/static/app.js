// 채팅 화면 : 입력을 서버(/api/chat)에 보내고 답을 대화에 붙입니다. (web 1단계)
// 본인 확인을 묻는 중(pending = "secret")이면 입력칸을 비밀번호 칸으로 바꾸고, 대화에는 "****" 로만 남깁니다.

const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("text");
const send = document.getElementById("send");

function add(text, kind) {
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  add(input.type === "password" ? "****" : text, "me");
  input.value = "";
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
    add(data.answer, "bot");
    input.type = data.pending === "secret" ? "password" : "text";
  } catch (e) {
    waiting.remove();
    add("서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.", "notice");
  }
  send.disabled = false;
  input.focus();
});
