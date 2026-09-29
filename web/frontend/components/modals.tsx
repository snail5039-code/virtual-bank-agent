"use client";

// 버튼 업무 확인 창의 내용들입니다. (예전 web/static/app.js 의 showConfirm, openTransfer, openReissue, openForm, openPicker)
// 어떤 창을 띄울지는 components/useActions.tsx 가 정합니다. 여기는 창 하나하나의 모양과 입력만 맡습니다.
//
// 순서 : (입력 창) → 다음 → 서버가 검사(/api/action/preview) → 처리안 확인 창 → 승인 → 본인 확인(아직이면) → 실행(/api/action/run) → 결과
// 입력 창에서 검사가 막히면 창은 그대로 두고 사유만 보여줘서 고치게 합니다.

import { useState } from "react";
import ProposalView from "@/components/ProposalView";
import { postJSON } from "@/lib/api";
import type { Address, Bank, CardRow, Preview, RunReply, TransferOptions } from "@/lib/types";
import { won } from "@/lib/types";

export type Params = Record<string, string>;
// 검사를 통과하면 처리안 확인 창으로 넘어갑니다.
export type OnPreviewed = (kind: string, target: string, params: Params, pre: Preview) => void;

async function preview(kind: string, target: string, params: Params) {
  return postJSON<Preview>("/api/action/preview", { kind, target, params });
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function Buttons({ next, onNext, onClose, disabled }: { next?: string; onNext?: () => void; onClose: () => void; disabled?: boolean }) {
  return (
    <div className="actions">
      {onNext && <button type="button" className="primary" disabled={disabled} onClick={onNext}>{next ?? "다음"}</button>}
      <button type="button" className={onNext ? "ghost" : "primary"} onClick={onClose} autoFocus={!onNext}>닫기</button>
    </div>
  );
}

// ---------------------------------------------------------------- 결과·사유 (닫기만)
export function Message({ text, tone, onClose }: { text: string; tone?: "ok" | "bad"; onClose: () => void }) {
  return (
    <>
      <div className={"modal-msg " + (tone ?? "")}>{text}</div>
      <Buttons onClose={onClose} />
    </>
  );
}

// ---------------------------------------------------------------- 처리안 확인 : 처리안 + (본인 확인 칸) + 승인 / 거절
type ConfirmProps = { kind: string; target: string; params: Params; pre: Preview;
                      onFinish: (text: string, tone?: "ok" | "bad") => void };

export function Confirm({ kind, target, params, pre, onFinish }: ConfirmProps) {
  const [secret, setSecret] = useState("");
  const [authError, setAuthError] = useState("");
  const [sending, setSending] = useState(false);

  async function run(approve: boolean) {
    // 승인하면 서버가 본인 확인 → 다시 검사 → 실행 → 처리 기록 → 저장 순서로 처리합니다. 거절은 기록만 남깁니다.
    setSending(true);
    const res = await postJSON<RunReply>("/api/action/run", { kind, target, params, approve, secret: pre.need_auth ? secret : null });
    if (res.auth_error) {            // 본인 확인이 틀림 : 창은 그대로 두고 다시 입력받습니다
      setAuthError(res.auth_error);
      setSecret("");
      setSending(false);
      return;
    }
    if (res.error) onFinish(res.error, "bad");
    else onFinish(res.answer ?? "", res.result === "완료" ? "ok" : undefined);
  }

  return (
    <>
      <div className="modal-head">처리안 확인</div>
      {pre.proposal && <ProposalView proposal={pre.proposal} />}
      {pre.need_auth && (
        <>
          <div className="auth-label">본인 확인 : 계좌 비밀번호, PIN, 휴대전화번호, 주민번호 뒷자리 중 하나</div>
          <input type="password" autoComplete="off" autoFocus value={secret} disabled={sending}
                 onChange={(e) => setSecret(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && !sending) run(true); }} />
          <div className="auth-error">{authError}</div>
        </>
      )}
      <div className="actions">
        <button type="button" className="primary" disabled={sending} autoFocus={!pre.need_auth} onClick={() => run(true)}>승인</button>
        <button type="button" className="ghost" disabled={sending} onClick={() => run(false)}>거절</button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- 이체 창 : 출금 · 입금 · 금액 · (예약 시각)
function tomorrowNine() {
  // 기본 예약 시각 : 내일 09:00 (이 컴퓨터 날짜 기준. toISOString 은 UTC 라 새벽에는 날짜가 하루 어긋납니다)
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T09:00";
}

type TransferProps = { opt: TransferOptions; from?: string; schedule?: boolean; onPreviewed: OnPreviewed; onClose: () => void };

export function TransferForm({ opt, from, schedule, onPreviewed, onClose }: TransferProps) {
  const [fromId, setFromId] = useState(from ?? opt.accounts[0]?.id ?? "");
  const [toId, setToId] = useState("");
  const [amount, setAmount] = useState("");
  const [useTime, setUseTime] = useState(!!schedule);
  const [at, setAt] = useState(tomorrowNine);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function next() {
    const params = { from: fromId, to: toId, amount, at: useTime ? at : "" };
    setSending(true);
    const pre = await preview("transfer", "", params);
    setSending(false);
    if (pre.error) setError(pre.error);
    else onPreviewed("transfer", "", params, pre);
  }

  return (
    <>
      <div className="modal-head">{useTime ? "예약 이체" : "이체"}</div>
      <Field label="출금 계좌">
        <select value={fromId} autoFocus={!from} onChange={(e) => setFromId(e.target.value)}>
          {opt.accounts.map((a) => <option key={a.id} value={a.id}>{a.name}  (잔액 {won(a.balance)}원)</option>)}
        </select>
      </Field>
      <Field label="입금 계좌">
        <select value={toId} autoFocus={!!from} onChange={(e) => setToId(e.target.value)}>
          <option value="">입금 계좌를 고르세요</option>
          {opt.targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </Field>
      <Field label="금액 (원)">
        <input inputMode="numeric" placeholder="예: 100000" value={amount} onChange={(e) => setAmount(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter" && !sending) next(); }} />
      </Field>
      <label className="check">
        <input type="checkbox" checked={useTime} onChange={(e) => setUseTime(e.target.checked)} />
        <span>예약 이체로 보내기</span>
      </label>
      {useTime && <Field label="예약 시각"><input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></Field>}
      <div className="auth-error">{error}</div>
      <Buttons onNext={next} onClose={onClose} disabled={sending} />
    </>
  );
}

// ---------------------------------------------------------------- 재발급 창 : 배송지(집 / 회사) 고르기
type ReissueProps = { card: CardRow; addresses: Address[]; onPreviewed: OnPreviewed; onClose: () => void };

export function ReissueForm({ card, addresses, onPreviewed, onClose }: ReissueProps) {
  const [picked, setPicked] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function next() {
    const params = { address: picked };
    setSending(true);
    const pre = await preview("reissue", card.id, params);
    setSending(false);
    if (pre.error) setError(pre.error);
    else onPreviewed("reissue", card.id, params, pre);
  }

  return (
    <>
      <div className="modal-head">카드 재발급</div>
      <div className="task">새 카드를 받을 배송지를 골라 주세요. ({card.name})</div>
      <div className="choices">
        {addresses.map((a) => (
          <label key={a.id} className="check">
            <input type="radio" name="address" checked={picked === a.id} onChange={() => setPicked(a.id)} />
            <span>{a.label}  {a.address}</span>
          </label>
        ))}
      </div>
      <div className="auth-error">{error}</div>
      <Buttons onNext={next} onClose={onClose} disabled={sending} />
    </>
  );
}

// ---------------------------------------------------------------- 입력 창 (등록처럼 칸만 채우면 되는 업무)
//   banks       : 은행 고르기 (서버의 은행 목록)
//   bankExample : 고른 은행의 계좌번호 모양을 예시로 보여줌. 숫자만 적어도 서버가 모양에 맞춰 줍니다
//   options     : [[값, 보이는 글], …] 이 있으면 고르기
//   secret      : 가리는 칸 (계좌 비밀번호)
export type FormField = { key: string; label: string; placeholder?: string; optional?: boolean;
                          banks?: boolean; bankExample?: boolean; secret?: boolean; options?: [string, string][] };
export type FormSpec = { title: string; kind: string; target?: string; fields: FormField[] };

type FieldsProps = { form: FormSpec; banks: Bank[]; onPreviewed: OnPreviewed; onClose: () => void };

export function FieldsForm({ form, banks, onPreviewed, onClose }: FieldsProps) {
  // 고르기 칸은 첫 번째 것을 골라 둔 채로 시작합니다. (화면에 보이는 것과 보낼 값이 같게)
  const [values, setValues] = useState<Params>(() => Object.fromEntries(form.fields.map((f) =>
    [f.key, f.banks ? banks[0]?.name ?? "" : f.options ? f.options[0]?.[0] ?? "" : ""])));
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const set = (key: string, value: string) => setValues((prev) => ({ ...prev, [key]: value }));
  const example = banks.find((b) => b.name === values.bank_name)?.example;

  async function next() {
    const target = form.target ?? "";       // 해지처럼 대상이 정해진 창이면 그 ID
    setSending(true);
    const pre = await preview(form.kind, target, values);
    setSending(false);
    if (pre.error) setError(pre.error);
    else onPreviewed(form.kind, target, values, pre);
  }

  return (
    <>
      <div className="modal-head">{form.title}</div>
      {form.fields.map((f, i) => (
        <Field key={f.key} label={f.label}>
          {f.banks || f.options ? (
            <select value={values[f.key]} autoFocus={i === 0} onChange={(e) => set(f.key, e.target.value)}>
              {f.banks ? banks.map((b) => <option key={b.name} value={b.name}>{b.name}</option>)
                       : f.options!.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          ) : (
            <input type={f.secret ? "password" : "text"} autoComplete="off" autoFocus={i === 0}
                   placeholder={f.bankExample ? (example ? "예: " + example : "") : f.placeholder ?? ""}
                   value={values[f.key]} onChange={(e) => set(f.key, e.target.value)} />
          )}
        </Field>
      ))}
      <div className="auth-error">{error}</div>
      <Buttons onNext={next} onClose={onClose} disabled={sending} />
    </>
  );
}

// ---------------------------------------------------------------- 고르기 창 : 빠른 실행에서 대상을 먼저 고릅니다
export type PickItem = { label: string; sub?: string; pick: () => void };

export function Picker({ title, items, empty, onClose }: { title: string; items: PickItem[]; empty: string; onClose: () => void }) {
  return (
    <>
      <div className="modal-head">{title}</div>
      {items.length ? (
        <div className="pick-list">
          {items.map((item, i) => (
            <button key={i} type="button" className="pick" onClick={item.pick}>
              <span>{item.label}</span><span className="sub">{item.sub ?? ""}</span>
            </button>
          ))}
        </div>
      ) : <div className="empty">{empty}</div>}
      <Buttons onClose={onClose} />
    </>
  );
}
