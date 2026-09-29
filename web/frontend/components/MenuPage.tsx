"use client";

// 메뉴 화면 (계좌, 거래 내역, 카드, 카드값, 예약 이체, 처리 기록). /api/view/<이름> 을 바로 읽어 표로 보여줍니다. (LLM 없음)
// 표의 버튼(잠그기, 내기, 취소 …)은 버튼 업무 창을 엽니다. (components/useActions.tsx)
// version 이 바뀌면(업무를 처리했거나 스케줄러 알림이 왔을 때) 다시 읽습니다.

import { useEffect, useState } from "react";
import { CARD_BADGE, REQUEST_BADGE } from "@/components/SidePanel";
import type { Actions } from "@/components/useActions";
import { getJSON } from "@/lib/api";
import type { AccountRow, BillRow, CardRow, RegisteredRow, RequestRow, ScheduleRow, TxRow } from "@/lib/types";
import { stamp, won } from "@/lib/types";

export type PageName = "accounts" | "transactions" | "cards" | "bills" | "schedules" | "requests";

const TITLES: Record<PageName, string> = {
  accounts: "계좌", transactions: "거래 내역", cards: "카드", bills: "카드값", schedules: "예약 이체", requests: "처리 기록",
};
const EMPTY: Record<PageName, string> = {
  accounts: "계좌가 없어요", transactions: "거래 내역이 없어요", cards: "카드가 없어요",
  bills: "청구서가 없어요", schedules: "걸어 둔 예약이 없어요", requests: "아직 처리한 업무가 없어요",
};

// headers : [제목, "num"(오른쪽 정렬) 또는 ""]   rows : 칸들 (글자 또는 요소)
function Table({ headers, rows }: { headers: [string, string][]; rows: React.ReactNode[][] }) {
  return (
    <table>
      <thead><tr>{headers.map(([text, cls], i) => <th key={i} className={cls}>{text}</th>)}</tr></thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r}>{row.map((cell, i) => <td key={i} className={headers[i][1]}>{cell}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function Act({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" className="act" onClick={onClick}>{label}</button>;
}

const Badge = ({ text, cls }: { text: string; cls: string }) => <span className={"badge " + cls}>{text}</span>;
const Money = ({ children }: { children: React.ReactNode }) => <span className="mono">{children}</span>;

type Props = { name: PageName; version: number; actions: Actions };

export default function MenuPage({ name, version, actions }: Props) {
  // 계좌 화면은 아래에 등록 계좌(상대 계좌)도 같이 보여줍니다.
  const [data, setData] = useState<{ rows: unknown[]; registered: RegisteredRow[] } | null>(null);
  const [accountFilter, setAccountFilter] = useState("");     // 거래 내역 고르기 (화면 안에서만 거릅니다)
  const [typeFilter, setTypeFilter] = useState("");

  useEffect(() => {
    let current = true;     // 불러오는 사이에 다른 메뉴로 갔으면 그리지 않습니다
    Promise.all([
      getJSON<unknown[]>("/api/view/" + name),
      name === "accounts" ? getJSON<RegisteredRow[]>("/api/view/registered") : Promise.resolve([]),
    ]).then(([rows, registered]) => { if (current) setData({ rows, registered }); });
    return () => { current = false; };
  }, [name, version]);

  let tools: React.ReactNode = null;
  let content: React.ReactNode = <div className="empty">불러오는 중...</div>;

  if (data) {
    const empty = <div className="empty">{EMPTY[name]}</div>;

    if (name === "accounts") {
      const rows = data.rows as AccountRow[];
      tools = <>
        <Act label="내 계좌 만들기" onClick={actions.openOpenForm} />
        <Act label="상대 계좌 등록" onClick={actions.openAccountForm} />
        <Act label="가상 입금" onClick={() => actions.quickAction("deposit")} />
      </>;
      content = <>
        {rows.length ? <Table headers={[["계좌", ""], ["은행 / 계좌번호", ""], ["용도", ""], ["잔액", "num"], ["", "num"]]}
          rows={rows.map((a) => [
            <>{a.name} {a.status === "suspended" && <Badge text="정지" cls="b-bad" />}</>,
            a.bank + " " + a.number, a.purpose, <Money key="m">{won(a.balance)}원</Money>,
            <span key="b" className="btns">
              <Act label="이체" onClick={() => actions.openTransfer({ from: a.id })} />
              {a.status === "suspended" ? <Act label="정지 풀기" onClick={() => actions.openAction("account_resume", a.id)} />
                                        : <Act label="정지" onClick={() => actions.openAction("account_suspend", a.id)} />}
              <Act label="해지" onClick={() => actions.closeAccount(a)} />
            </span>,
          ])} /> : empty}
        <h3 className="sub-title">등록 계좌</h3>
        {data.registered.length ? <Table headers={[["별명", ""], ["은행 / 계좌번호", ""], ["예금주", ""], ["", "num"]]}
          rows={data.registered.map((r) => [r.name, r.bank + " " + r.number, r.holder,
            <Act key="d" label="삭제" onClick={() => actions.openAction("registered_delete", r.id)} />])} />
          : <div className="empty">등록한 상대 계좌가 없어요</div>}
      </>;
    }

    if (name === "transactions") {
      const all = data.rows as TxRow[];
      const rows = all.filter((r) => (!accountFilter || r.account === accountFilter) && (!typeFilter || r.type === typeFilter));
      tools = <>
        <select value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}>
          <option value="">모든 계좌</option>
          {[...new Set(all.map((r) => r.account))].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">입금·출금</option><option value="입금">입금</option><option value="출금">출금</option>
        </select>
      </>;
      content = rows.length ? <Table headers={[["날짜", ""], ["계좌", ""], ["내용", ""], ["금액", "num"]]}
        rows={rows.map((t) => [<Money key="d">{stamp(t.at)}</Money>, t.account,
          [t.merchant, t.card && "(" + t.card + ")"].filter(Boolean).join(" ") || t.type,
          <Money key="m">{(t.type === "출금" ? "- " : "+ ") + won(t.amount)}원</Money>])} /> : empty;
    }

    if (name === "cards") {
      const rows = data.rows as CardRow[];
      tools = <Act label="카드 등록" onClick={actions.openCardRegister} />;
      // 카드 상태에 따라 : 사용 가능 → 잠그기, 잠금 → 잠금 풀기, 분실 정지 → 재발급. 해지 전이면 해지도. 해지한 카드는 지우기만.
      content = rows.length ? <Table headers={[["카드", ""], ["종류", ""], ["연결 계좌", ""], ["상태", ""], ["", "num"]]}
        rows={rows.map((c) => [c.name, c.type + (c.bank ? " / " + c.bank : ""), c.account,
          <Badge key="s" text={c.label} cls={CARD_BADGE[c.status] ?? "b-plain"} />,
          <span key="b" className="btns">
            {c.status === "cancelled" ? <Act label="지우기" onClick={() => actions.openAction("card_hide", c.id)} /> : <>
              {c.status === "active" && <Act label="잠그기" onClick={() => actions.openAction("card_lock", c.id)} />}
              {c.status === "locked" && <Act label="잠금 풀기" onClick={() => actions.openAction("card_unlock", c.id)} />}
              {c.status === "lost" && <Act label="재발급" onClick={() => actions.openReissue(c)} />}
              <Act label="해지" onClick={() => actions.openAction("card_cancel", c.id)} />
            </>}
          </span>,
        ])} /> : empty;
    }

    if (name === "bills") {
      const rows = data.rows as BillRow[];
      tools = <Act label="가상 카드값" onClick={actions.openBillAdd} />;
      content = rows.length ? <Table headers={[["카드", ""], ["청구 월", ""], ["청구액", "num"], ["남은 금액", "num"], ["기한", ""], ["상태", ""], ["", "num"]]}
        rows={rows.map((s) => [s.card, s.month, <Money key="t">{won(s.total)}</Money>, <Money key="r">{won(s.remaining)}</Money>,
          <Money key="d">{s.due}</Money>,
          <Badge key="s" text={s.label} cls={s.status === "paid" ? "b-ok" : s.status === "partial" ? "b-warn" : "b-bad"} />,
          s.remaining > 0 ? <Act key="p" label="전체 내기" onClick={() => actions.openAction("bill_pay", s.id)} /> : "",
        ])} /> : empty;
    }

    if (name === "schedules") {
      const rows = data.rows as ScheduleRow[];
      const cls = (s: string) => (s === "완료" ? "b-ok" : s === "실패" ? "b-bad" : s === "예약" ? "b-warn" : "b-plain");
      tools = <Act label="예약 이체 하기" onClick={() => actions.openTransfer({ schedule: true })} />;
      content = rows.length ? <Table headers={[["예약 시각", ""], ["출금 → 입금", ""], ["금액", "num"], ["상태", ""], ["", "num"]]}
        rows={rows.map((s) => [<Money key="a">{stamp(s.at)}</Money>, s.from + " → " + s.to, <Money key="m">{won(s.amount)}원</Money>,
          <Badge key="s" text={s.status} cls={cls(s.status)} />,
          s.status === "예약" ? <Act key="c" label="취소" onClick={() => actions.openAction("schedule_cancel", s.id)} /> : "",
        ])} /> : empty;
    }

    if (name === "requests") {
      const rows = data.rows as RequestRow[];
      content = rows.length ? <Table headers={[["시각", ""], ["업무", ""], ["내용", ""], ["결과", ""]]}
        rows={rows.map((r) => [<Money key="a">{stamp(r.at)}</Money>, r.task,
          <div key="c" className="content">{Object.entries(r.content ?? {}).map(([k, v]) => k + " : " + v).join("\n")}</div>,
          <Badge key="s" text={r.status} cls={REQUEST_BADGE[r.status] ?? "b-plain"} />,
        ])} /> : empty;
    }
  }

  return (
    <section className="page-view">
      <div className="page-head"><h2>{TITLES[name]}</h2><div className="page-tools">{tools}</div></div>
      {content}
    </section>
  );
}
