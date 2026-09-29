// 오른쪽 패널 : 진행 상황, 카드, 카드값, 예약 이체, 최근 처리, 알림. 값은 /api/summary 에서 옵니다. (읽기만)

import type { Pending, Summary } from "@/lib/types";
import { won } from "@/lib/types";

export const CARD_BADGE: Record<string, string> = { active: "b-ok", locked: "b-warn", lost: "b-bad" };
export const REQUEST_BADGE: Record<string, string> = { "완료": "b-ok", "실패": "b-bad" };     // 그 밖(거절·취소)은 옅은 회색

// 진행 상황 : 변경 업무의 순서입니다. 멈춘 종류로 지금 어디인지 정합니다.
const STEPS = ["요청 이해", "검사", "본인 확인", "승인 대기", "실행과 저장"];
const NOW_STEP: Record<Pending, number> = { question: 0, secret: 2, approval: 3 };

function shortTime(iso: string) {
  // "2026-09-30T09:00:00" → "09-30 09:00"
  return iso.slice(5, 10) + " " + iso.slice(11, 16);
}

function Line({ name, children }: { name: string; children: React.ReactNode }) {
  return <div className="line"><span>{name}</span>{children}</div>;
}

function List({ empty, children }: { empty: string; children: React.ReactNode[] }) {
  return children.length ? <>{children}</> : <div className="empty">{empty}</div>;
}

type Props = { summary: Summary | null; pending: Pending | null; alerts: string[] };

export default function SidePanel({ summary, pending, alerts }: Props) {
  const now = pending ? NOW_STEP[pending] : undefined;
  return (
    <aside className="panel">
      <section>
        <h3>진행 상황</h3>
        <div className="steps">
          {now === undefined ? <div className="empty">진행 중인 업무가 없어요</div> : STEPS.map((name, i) => {
            if (i < now) return <div key={name}>✓ {name}</div>;
            if (i === now) return <div key={name} className="now">‖ {name}{pending === "question" && " (질문에 답해 주세요)"}</div>;
            return <div key={name} className="todo">○ {name}</div>;
          })}
        </div>
      </section>
      <section>
        <h3>카드</h3>
        <List empty="카드가 없어요">
          {(summary?.cards ?? []).map((c, i) => (
            <Line key={i} name={c.name}><span className={"badge " + (CARD_BADGE[c.status] ?? "b-plain")}>{c.label}</span></Line>
          ))}
        </List>
      </section>
      <section>
        <h3>카드값</h3>
        <List empty="낼 카드값이 없어요">
          {summary?.bills.count ? [
            <Line key="bills" name={"낼 돈이 남은 청구서 " + summary.bills.count + "건"}>
              <span className="mono">{won(summary.bills.amount)}원</span>
            </Line>,
          ] : []}
        </List>
      </section>
      <section>
        <h3>예약 이체</h3>
        <List empty="걸어 둔 예약이 없어요">
          {(summary?.schedules ?? []).map((s, i) => (
            <Line key={i} name={shortTime(s.at) + "  " + s.to}><span className="mono">{won(s.amount)}원</span></Line>
          ))}
        </List>
      </section>
      <section>
        <h3>최근 처리</h3>
        <List empty="아직 처리한 업무가 없어요">
          {(summary?.requests ?? []).map((r, i) => (
            <Line key={i} name={r.task}><span className={"badge " + (REQUEST_BADGE[r.status] ?? "b-plain")}>{r.status}</span></Line>
          ))}
        </List>
      </section>
      {alerts.length > 0 && (
        <section>
          <h3>알림</h3>
          {alerts.map((text, i) => <div key={i} className="alert">{text}</div>)}
        </section>
      )}
    </aside>
  );
}
