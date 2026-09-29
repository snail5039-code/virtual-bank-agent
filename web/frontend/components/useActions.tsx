"use client";

// 버튼 업무 : 메뉴 화면의 버튼과 위쪽 빠른 실행이 LLM 없이 바로 하는 업무입니다.
// 지금 어떤 창이 떠 있는지(modal)를 하나만 들고, 창 안에서 다음 창으로 넘어가며 바꿉니다.
//   입력 창(이체·재발급·등록 …) → 처리안 확인 → 결과
// 에이전트가 답하는 중(busy)이면 새 창을 열지 않습니다. (서버도 에이전트가 멈춰 있는 동안은 막습니다)

import { useState } from "react";
import { Confirm, FieldsForm, Message, Picker, ReissueForm, TransferForm } from "@/components/modals";
import type { FormSpec, OnPreviewed, Params, PickItem } from "@/components/modals";
import { getJSON, postJSON } from "@/lib/api";
import type { AccountRow, Address, Bank, BillRow, CardRow, Preview, TransferOptions } from "@/lib/types";
import { won } from "@/lib/types";

type ModalState =
  | { type: "loading" }
  | { type: "message"; text: string; tone?: "ok" | "bad" }
  | { type: "confirm"; kind: string; target: string; params: Params; pre: Preview }
  | { type: "transfer"; opt: TransferOptions; from?: string; schedule?: boolean }
  | { type: "reissue"; card: CardRow; addresses: Address[] }
  | { type: "form"; form: FormSpec; banks: Bank[] }
  | { type: "picker"; title: string; items: PickItem[]; empty: string };

export type QuickKind = "transfer" | "lock" | "bill" | "reissue" | "deposit";

const ACCOUNT_FORM: FormSpec = {
  title: "상대 계좌 등록", kind: "account_register",
  fields: [
    { key: "bank_name", label: "은행", banks: true },
    { key: "account_number", label: "계좌번호 (은행마다 자릿수가 달라요)", bankExample: true },
    { key: "holder_name", label: "예금주", placeholder: "예: 이영희" },
    { key: "nickname", label: "별명 (안 쓰면 예금주 이름)", placeholder: "예: 친구 영희", optional: true },
  ],
};
const OPEN_FORM: FormSpec = {
  title: "내 계좌 만들기", kind: "account_open",
  fields: [
    { key: "bank_name", label: "은행", banks: true },
    { key: "account_number", label: "계좌번호 (직접 정해요. 은행마다 자릿수가 달라요)", bankExample: true },
    { key: "nickname", label: "별명", placeholder: "예: 비상금" },
    { key: "purpose", label: "용도 (선택)", placeholder: "예: 급할 때 쓰는 돈", optional: true },
    { key: "password", label: "계좌 비밀번호 (숫자 4자리)", secret: true },
  ],
};

export function useActions(busy: boolean, onChanged: () => void) {
  const [modal, setModal] = useState<ModalState | null>(null);
  const close = () => setModal(null);
  const toConfirm: OnPreviewed = (kind, target, params, pre) => setModal({ type: "confirm", kind, target, params, pre });

  async function openAction(kind: string, target: string, params: Params = {}) {
    // 입력할 것이 없는 업무 (잠그기, 해지, 전체 내기 …) : 바로 검사하고 처리안 확인으로
    if (busy) return;
    setModal({ type: "loading" });
    const pre = await postJSON<Preview>("/api/action/preview", { kind, target, params });
    if (pre.error) setModal({ type: "message", text: pre.error, tone: "bad" });
    else toConfirm(kind, target, params, pre);
  }

  // 이체 창.  from : 미리 골라 둘 출금 계좌 (계좌 화면의 이체 버튼)  schedule : 예약 시각 칸을 켠 채로 (예약 이체 화면)
  async function openTransfer(options: { from?: string; schedule?: boolean } = {}) {
    if (busy) return;
    setModal({ type: "loading" });
    const opt = await getJSON<TransferOptions>("/api/view/transfer_options");
    setModal({ type: "transfer", opt, ...options });
  }

  async function openReissue(card: CardRow) {
    if (busy) return;
    setModal({ type: "loading" });
    const addresses = await getJSON<Address[]>("/api/view/addresses");
    setModal({ type: "reissue", card, addresses });
  }

  async function openForm(form: FormSpec) {
    if (busy) return;
    setModal({ type: "loading" });
    // 은행 칸이 있으면 서버의 은행 목록(계좌번호 예시 포함)을 먼저 받아 옵니다.
    const banks = form.fields.some((f) => f.banks) ? await getJSON<Bank[]>("/api/view/banks") : [];
    setModal({ type: "form", form, banks });
  }

  function openPicker(title: string, items: PickItem[], empty: string) {
    if (busy) return;
    setModal({ type: "picker", title, items, empty });
  }

  async function myAccounts() {
    return (await getJSON<TransferOptions>("/api/view/transfer_options")).accounts;
  }

  async function closeAccount(a: AccountRow) {
    // 잔액이 없으면 바로 확인으로, 남아 있으면 먼저 남은 돈을 받을 계좌(내 다른 계좌 / 등록 계좌)를 고르게 합니다.
    if (a.balance <= 0) { openAction("account_close", a.id); return; }
    const opt = await getJSON<TransferOptions>("/api/view/transfer_options");
    openForm({
      title: "계좌 해지", kind: "account_close", target: a.id,
      fields: [{ key: "to", label: "남은 돈 " + won(a.balance) + "원을 받을 계좌",
                 options: opt.targets.filter((t) => t.id !== a.id).map((t) => [t.id, t.name]) }],
    });
  }

  async function openCardRegister() {
    const accounts = await myAccounts();     // 결제 계좌 = 내 계좌
    openForm({
      title: "카드 등록", kind: "card_register",
      fields: [
        { key: "bank_name", label: "은행", banks: true },
        { key: "card_number", label: "카드 번호 (16자리)", placeholder: "예: 1234-5678-1234-5678" },
        { key: "card_type", label: "종류", options: [["체크", "체크카드"], ["신용", "신용카드"]] },
        { key: "account_id", label: "결제 계좌", options: accounts.map((a) => [a.id, a.name]) },
        { key: "name", label: "별칭 (안 쓰면 은행 + 종류)", placeholder: "예: 장보기 카드", optional: true },
      ],
    });
  }

  async function openBillAdd() {
    // 가상 카드값 : 신용카드를 골라 이번 달 청구서에 시험용 금액을 더합니다. (만든 뒤 "전체 내기" 로 냅니다)
    const cards = (await getJSON<CardRow[]>("/api/view/cards")).filter((c) => c.type === "신용" && c.status !== "cancelled");
    if (!cards.length) { openPicker("가상 카드값", [], "신용카드가 없어요. 카드 화면에서 신용카드를 먼저 등록해 주세요"); return; }
    openForm({
      title: "가상 카드값", kind: "bill_add",
      fields: [
        { key: "card", label: "신용카드", options: cards.map((c) => [c.id, c.name + (c.account ? "  (결제 계좌 " + c.account + ")" : "")]) },
        { key: "amount", label: "금액 (한 번에 1,000만원까지)", placeholder: "예: 150000" },
      ],
    });
  }

  async function quickAction(kind: QuickKind) {
    // 위쪽 빠른 실행 : 이체는 이체 창, 가상 입금은 입력 창, 나머지는 대상을 고르는 창을 엽니다.
    if (busy) return;
    if (kind === "transfer") { openTransfer(); return; }
    if (kind === "deposit") {
      const accounts = await myAccounts();
      if (!accounts.length) { openPicker("가상 입금", [], "계좌가 없어요. 계좌 화면에서 '내 계좌 만들기' 를 먼저 해 주세요"); return; }
      openForm({
        title: "가상 입금", kind: "deposit",
        fields: [
          { key: "account", label: "입금할 내 계좌", options: accounts.map((a) => [a.id, a.name + "  (잔액 " + won(a.balance) + "원)"]) },
          { key: "amount", label: "금액 (한 번에 1,000만원까지)", placeholder: "예: 100000" },
        ],
      });
      return;
    }
    if (kind === "bill") {
      const bills = (await getJSON<BillRow[]>("/api/view/bills")).filter((s) => s.remaining > 0);
      openPicker("어떤 카드값을 낼까요?", bills.map((s) => ({
        label: s.card + " " + s.month, sub: won(s.remaining) + "원  기한 " + s.due,
        pick: () => openAction("bill_pay", s.id),
      })), "낼 카드값이 없어요");
      return;
    }
    const cards = await getJSON<CardRow[]>("/api/view/cards");
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

  function body(m: ModalState) {
    switch (m.type) {
      case "loading": return <div className="empty">불러오는 중...</div>;
      case "message": return <Message text={m.text} tone={m.tone} onClose={close} />;
      case "confirm":
        return <Confirm kind={m.kind} target={m.target} params={m.params} pre={m.pre} onFinish={(text, tone) => {
          onChanged();     // 잔액·패널·보고 있던 메뉴 화면을 새 값으로
          setModal({ type: "message", text, tone });
        }} onClose={close} />;
      case "transfer": return <TransferForm opt={m.opt} from={m.from} schedule={m.schedule} onPreviewed={toConfirm} onClose={close} />;
      case "reissue": return <ReissueForm card={m.card} addresses={m.addresses} onPreviewed={toConfirm} onClose={close} />;
      case "form": return <FieldsForm form={m.form} banks={m.banks} onPreviewed={toConfirm} onClose={close} />;
      case "picker": return <Picker title={m.title} items={m.items} empty={m.empty} onClose={close} />;
    }
  }

  const element = modal && (
    <div className="modal-back">
      <div className="modal-box" role="dialog" aria-modal="true">{body(modal)}</div>
    </div>
  );

  return {
    element, openAction, openTransfer, openReissue, closeAccount, quickAction, openCardRegister, openBillAdd,
    openOpenForm: () => openForm(OPEN_FORM), openAccountForm: () => openForm(ACCOUNT_FORM),
  };
}

export type Actions = ReturnType<typeof useActions>;
