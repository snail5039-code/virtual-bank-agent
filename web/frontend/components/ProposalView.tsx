// 처리안 내용을 그립니다. 대화의 처리안 카드와 (3단계) 버튼 업무의 확인 창이 같이 씁니다.
// 금액 칸은 크게, 주의 칸은 노란 안내로, 나머지는 이름 : 값 줄로 보여줍니다.

import type { Proposal } from "@/lib/types";

// 처리안에서 크게 보여줄 금액 칸 이름 (업무마다 이름이 다릅니다)
const AMOUNT_LABELS = ["총액", "낼 금액", "합계", "입금액", "청구액"];

export default function ProposalView({ proposal }: { proposal: Proposal }) {
  const amount = proposal.rows.find(([label]) => AMOUNT_LABELS.includes(label));
  return (
    <>
      <div className="task">{proposal.task}</div>
      {amount && (
        <div className="amount mono">
          {amount[1].replace(/원$/, "")}
          {amount[1].endsWith("원") && <small>원</small>}
        </div>
      )}
      {proposal.rows.map(([label, value], i) => {
        if (amount && label === amount[0]) return null;
        if (label === "주의") return <div key={i} className="warn">{value}</div>;
        return (
          <div key={i} className="row">
            <span>{label}</span>
            <span className={/[0-9]/.test(value) ? "mono" : ""}>{value}</span>
          </div>
        );
      })}
    </>
  );
}
