"use client";

// 에이전트 대화 화면. (예전 web/static/app.js 의 대화 부분을 옮김)
//   - 입력을 /api/chat 에 보내고 답을 대화에 붙입니다. 답한 업무 분야(domain)마다 다른 캐릭터가 말합니다.
//   - 본인 확인을 묻는 중(pending = "secret")이면 입력칸을 비밀번호 칸으로 바꾸고, 대화에는 "****" 로만 남깁니다.
//   - 승인을 기다리면(pending = "approval") 글자 대신 처리안 카드를 그립니다. 버튼은 "승인" / "거절" 을 치는 것과 같습니다.
//   - 처리 중(busy)에는 새로 보내지 않고 "답하는 중" 안내만 띄웁니다. (두 번 보내지 않게)
//   - 켤 때 : 재시작 복구(/api/recovery)를 묻고, 새로고침 전에 멈춰 있던 질문·처리안(/api/waiting)을 다시 그립니다.
//   - 10초마다 스케줄러 알림(/api/alerts)을 가져옵니다.

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { BotAvatar, UserAvatar, characterOf } from "@/components/Avatar";
import ProposalView from "@/components/ProposalView";
import { getJSON, postJSON } from "@/lib/api";
import type { Domain, Pending, Proposal, RecoveryRecord, Reply } from "@/lib/types";

// 대화 한 줄. label 이 null 이면 아직 답을 기다리는 카드(버튼이 살아 있음), 글자면 사용자가 한 일(승인함 등)
type Item =
  | { id: number; kind: "me"; text: string }
  | { id: number; kind: "bot"; text: string; domain: Domain | null }
  | { id: number; kind: "notice"; text: string }
  | { id: number; kind: "proposal"; proposal: Proposal; domain: Domain | null; label: string | null }
  | { id: number; kind: "recovery"; record: RecoveryRecord; label: string | null };
type WithoutId<T> = T extends unknown ? Omit<T, "id"> : never;     // 종류마다 따로 id 를 뺍니다
type NewItem = WithoutId<Item>;

const PLACEHOLDER = "요청을 입력하세요";
const WELCOME = "무엇을 도와드릴까요? 예: 내 계좌 목록과 잔액 보여줘";

type Props = {
  userName: string;
  onChanged: () => void;                     // 데이터가 바뀌었을 수 있음 → 잔액·패널을 다시 읽기
  onPending: (p: Pending | null) => void;    // 오른쪽 진행 상황
  onAlerts: (lines: string[]) => void;       // 오른쪽 알림
  onBusy: (busy: boolean) => void;           // 답하는 중에는 버튼 업무 창도 열지 않게
};

export default function Chat({ userName, onChanged, onPending, onAlerts, onBusy }: Props) {
  const [items, setItems] = useState<Item[]>([{ id: 0, kind: "bot", text: WELCOME, domain: null }]);
  const [text, setText] = useState("");
  const [placeholder, setPlaceholder] = useState(PLACEHOLDER);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);             // 화면을 다시 그리기 전에도 바로 막으려고 ref 로도 둡니다
  const busyNoteRef = useRef<number | null>(null);
  const nextId = useRef(1);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function add(item: NewItem) {
    const id = nextId.current++;
    setItems((prev) => [...prev, { ...item, id } as Item]);
    return id;
  }
  const remove = (id: number) => setItems((prev) => prev.filter((it) => it.id !== id));

  function closeCard(label: string) {
    // 답을 보낸 카드는 버튼을 막고, 사용자가 무엇을 했는지 표시합니다. (결과는 아래 에이전트 답에 나옵니다)
    setItems((prev) => prev.map((it) => (it.kind === "proposal" && it.label === null ? { ...it, label } : it)));
  }

  function showReply(data: Reply) {
    // 답(또는 멈춘 질문·처리안)을 대화에 붙이고, 입력칸과 진행 상황을 멈춘 종류에 맞춥니다.
    if (data.proposal) add({ kind: "proposal", proposal: data.proposal, domain: data.domain, label: null });
    else add({ kind: "bot", text: data.answer ?? "", domain: data.domain });
    // 입력칸 종류가 바뀌면(보통 칸 ↔ 비밀번호 칸) 기다리는 동안 쳐 둔 글자를 지웁니다.
    // 그대로 두면 다른 요청으로 쓴 글이 비밀번호 답으로 들어갈 수 있습니다.
    if ((pending === "secret") !== (data.pending === "secret")) setText("");
    setPending(data.pending);
    onPending(data.pending);
  }

  async function call(url: string, payload: unknown) {
    // 서버에 보내고, 돌아온 답을 화면에 붙입니다. 채팅과 재시작 복구가 같이 씁니다.
    busyRef.current = true;
    setBusy(true);
    onBusy(true);
    setText("");
    setPlaceholder(PLACEHOLDER);
    const waiting = add({ kind: "notice", text: "에이전트가 작업 중입니다..." });
    try {
      const data = await postJSON<Reply>(url, payload);
      remove(waiting);
      const notices = data.notices ?? [];
      for (const line of notices) add({ kind: "notice", text: line });
      onAlerts(notices);
      showReply(data);
      onChanged();
    } catch {
      remove(waiting);
      add({ kind: "notice", text: "서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요." });
    }
    busyRef.current = false;
    setBusy(false);
    onBusy(false);
    if (busyNoteRef.current !== null) {
      remove(busyNoteRef.current);
      busyNoteRef.current = null;
    }
    inputRef.current?.focus();
  }

  function submit(value: string, cardLabel?: string) {
    if (busyRef.current) {
      // 보내지 않고 입력은 입력칸에 그대로 둡니다. 답이 오면 안내를 지웁니다.
      if (busyNoteRef.current === null) {
        busyNoteRef.current = add({ kind: "notice", text: "에이전트가 답하는 중이에요. 답이 오면 다시 보내 주세요. (입력한 내용은 그대로 있어요)" });
      }
      return;
    }
    add({ kind: "me", text: pending === "secret" ? "****" : value });
    closeCard(cardLabel ?? "수정 요청");
    call("/api/chat", { text: value });
  }

  function chooseRecovery(id: number, again: boolean) {
    // 재시작 복구 카드 : 다시 하면 원래 요청으로 처음부터 (승인도 다시), 지우면 기록만 지웁니다.
    if (busyRef.current) return;
    setItems((prev) => prev.map((it) => (it.id === id && it.kind === "recovery" ? { ...it, label: again ? "다시 진행" : "지움" } : it)));
    add({ kind: "me", text: again ? "처음부터 다시" : "지우기" });
    call("/api/recovery", { again });
  }

  async function newChat() {
    // 서버의 내 에이전트 세션을 새로 만들고 대화를 비웁니다. 진행 중인 질문·승인은 취소되므로 먼저 묻습니다. (데이터는 그대로)
    if (busyRef.current) return;
    if (pending && !confirm("진행 중인 업무가 있어요. 새 대화를 시작하면 그 업무는 취소됩니다. 계속할까요?")) return;
    await postJSON("/api/new_chat");
    setItems([{ id: nextId.current++, kind: "bot", text: "새 대화를 시작했어요. " + WELCOME, domain: null }]);
    setText("");
    setPlaceholder(PLACEHOLDER);
    setPending(null);
    onPending(null);
    onChanged();
    inputRef.current?.focus();
  }

  // 켤 때 한 번 : 재시작 복구 → 새로고침 전 업무 이어서 보기
  const loadOnce = useEffectEvent(async () => {
    const { record } = await getJSON<{ record: RecoveryRecord | null }>("/api/recovery");
    if (record) add({ kind: "recovery", record, label: null });
    const data = await getJSON<Reply>("/api/waiting");
    if (data.pending) {
      add({ kind: "notice", text: "새로고침 전에 진행하던 업무예요. 이어서 답해 주세요." });
      showReply(data);
    }
  });
  const started = useRef(false);     // 개발 모드(StrictMode)는 effect 를 두 번 부르므로 한 번만 하게 막습니다
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    loadOnce();
  }, []);

  // 스케줄러 알림 : 서버의 30초 스케줄러가 입력 없이 실행한 결과를 10초마다 가져옵니다.
  const pollAlerts = useEffectEvent(async () => {
    try {
      const { alerts } = await getJSON<{ alerts: string[] }>("/api/alerts");
      if (!alerts.length) return;
      for (const line of alerts) add({ kind: "notice", text: line });
      onAlerts(alerts);
      onChanged();
    } catch {
      // 서버가 꺼져 있으면 다음에 다시 봅니다.
    }
  });
  useEffect(() => {
    const timer = setInterval(pollAlerts, 10_000);
    return () => clearInterval(timer);
  }, []);

  // 새 줄이 붙으면 맨 아래로 내립니다.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [items]);

  return (
    <section className="view">
      <div className="log" ref={logRef}>
        {items.map((it) => {
          if (it.kind === "me") {
            return (
              <div key={it.id} className="me-row">
                <div className="msg me">{it.text}</div>
                <UserAvatar name={userName} />
              </div>
            );
          }
          if (it.kind === "notice") return <div key={it.id} className="notice">{it.text}</div>;
          const domain = it.kind === "recovery" ? null : it.domain;
          return (
            <div key={it.id} className="bot-row">
              <BotAvatar domain={domain} />
              <div className="bot-col">
                <div className="speaker">{characterOf(domain).name}</div>
                {it.kind === "bot" && <div className="msg bot">{it.text}</div>}
                {it.kind === "proposal" && (
                  <div className="card">
                    <div className="card-head">
                      처리안 확인<span className="badge">{it.label ?? "승인 대기"}</span>
                    </div>
                    <div className="card-body">
                      <ProposalView proposal={it.proposal} />
                      {it.proposal.retry && <div className="warn">답을 알아듣지 못했어요. 버튼을 누르거나 바꿀 내용을 적어 주세요.</div>}
                      <div className="actions">
                        <button type="button" className="primary" disabled={it.label !== null} onClick={() => submit("승인", "승인함")}>승인</button>
                        <button type="button" className="ghost" disabled={it.label !== null} onClick={() => {
                          setPlaceholder("바꿀 내용을 입력하세요. 예: 5만원만");
                          inputRef.current?.focus();
                        }}>수정</button>
                        <button type="button" className="ghost" disabled={it.label !== null} onClick={() => submit("거절", "거절함")}>거절</button>
                      </div>
                    </div>
                  </div>
                )}
                {it.kind === "recovery" && (
                  <div className="card">
                    <div className="card-head">
                      진행 중이던 업무<span className={"badge " + (it.label ? "b-plain" : "b-warn")}>{it.label ?? it.record.kind}</span>
                    </div>
                    <div className="card-body">
                      <div className="task">{it.record.when} 요청이 끝나기 전에 종료되었어요.</div>
                      <div className="amount">{it.record.request_text}</div>
                      <div className="warn">처음부터 다시 진행하면 잔액과 카드 상태를 다시 확인하고, 승인도 다시 받아요.</div>
                      <div className="actions">
                        <button type="button" className="primary" disabled={it.label !== null} onClick={() => chooseRecovery(it.id, true)}>처음부터 다시</button>
                        <button type="button" className="ghost" disabled={it.label !== null} onClick={() => chooseRecovery(it.id, false)}>지우기</button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <form className="chat-form" onSubmit={(e) => {
        e.preventDefault();
        const value = text.trim();
        if (value) submit(value);
      }}>
        <button type="button" className="ghost" title="대화를 비우고 새로 시작합니다" onClick={newChat}>새 대화</button>
        <input ref={inputRef} type={pending === "secret" ? "password" : "text"} autoComplete="off" placeholder={placeholder}
               value={text} onChange={(e) => setText(e.target.value)} />
        {/* 보내기는 흐리게만 합니다. disabled 로 막으면 Enter 가 아예 안 먹어서 "답하는 중" 안내도 못 띄웁니다 */}
        <button type="submit" className={busy ? "waiting" : ""}>보내기</button>
      </form>
    </section>
  );
}
