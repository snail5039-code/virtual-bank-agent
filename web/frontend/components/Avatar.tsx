// 대화 옆 캐릭터. 답한 업무 분야(1단 supervisor 가 고른 domain)마다 다른 친구가 말합니다.
//   뱅키 : 안내 (분야 없음 · 처음 인사)   머니 : 계좌   카디 : 카드   로기 : 처리 결과
// 얼굴은 동그라미 + 눈 + 입이고, 머리 위 장식만 다릅니다. 색은 globals.css 의 파스텔 색 이름을 써서 다크 모드에서도 맞춰집니다.

import type { Domain } from "@/lib/types";

type Character = { name: string; bg: string; fg: string; hat: React.ReactNode };

const CHARACTERS: Record<"bank" | "money" | "card" | "log", Character> = {
  // 더듬이
  bank: { name: "뱅키", bg: "var(--info-bg)", fg: "var(--info-text)",
          hat: <><line x1="16" y1="7" x2="16" y2="3" /><circle cx="16" cy="2.5" r="1.6" fill="currentColor" /></> },
  // 새싹 (돈이 자라요)
  money: { name: "머니", bg: "var(--ok-bg)", fg: "var(--ok-text)",
           hat: <><line x1="16" y1="7" x2="16" y2="3.5" /><path d="M16 4.5 C 13 2, 11 3.5, 12 5.5 C 13.5 6, 15 5.5, 16 4.5 Z" fill="currentColor" /></> },
  // 작은 카드
  card: { name: "카디", bg: "var(--warn-bg)", fg: "var(--warn-text)",
          hat: <><rect x="11.5" y="1.5" width="9" height="6" rx="1.2" fill="var(--surface)" /><line x1="11.5" y1="3.6" x2="20.5" y2="3.6" /></> },
  // 안경 (기록을 꼼꼼히 봐요)
  log: { name: "로기", bg: "var(--bad-bg)", fg: "var(--bad-text)",
         hat: <><circle cx="12.5" cy="17" r="3" /><circle cx="19.5" cy="17" r="3" /><line x1="15.5" y1="17" x2="16.5" y2="17" /></> },
};

export function characterOf(domain: Domain | null) {
  if (domain === "계좌") return CHARACTERS.money;
  if (domain === "카드") return CHARACTERS.card;
  if (domain === "결과") return CHARACTERS.log;
  return CHARACTERS.bank;
}

export function BotAvatar({ domain }: { domain: Domain | null }) {
  const c = characterOf(domain);
  return (
    <svg className="avatar" viewBox="0 0 32 32" aria-hidden="true" style={{ color: c.fg }}>
      <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none">
        <circle cx="16" cy="18" r="11" fill={c.bg} />
        {c.hat}
        <circle cx="12.5" cy="17" r="1.3" fill="currentColor" stroke="none" />
        <circle cx="19.5" cy="17" r="1.3" fill="currentColor" stroke="none" />
        <path d="M12.5 21.5 Q 16 24.5, 19.5 21.5" />
      </g>
    </svg>
  );
}

// 내 말풍선 옆 동그라미 : 이름 첫 글자
export function UserAvatar({ name }: { name: string }) {
  return <span className="avatar user-avatar" aria-hidden="true">{name.slice(0, 1) || "나"}</span>;
}
