// FastAPI 가 돌려주는 값의 모양입니다. (web/server.py 의 /api/summary, /api/chat 등)

export type Pending = "question" | "secret" | "approval";

// 답한 업무 분야. 1단 supervisor 가 고릅니다. 대화 옆 캐릭터를 이걸로 정합니다.
export type Domain = "계좌" | "카드" | "결과" | "없음";

export type Summary = {
  user: string;
  authenticated: boolean;
  total: number;
  accounts: { name: string; balance: number }[];
  cards: { name: string; status: string; label: string }[];
  bills: { count: number; amount: number };
  schedules: { at: string; to: string; amount: number }[];
  requests: { task: string; status: string; at: string }[];
};

// 승인을 기다리는 처리안. rows 는 [이름, 값] 줄들입니다. (예: ["출금", "생활비 (…)"])
export type Proposal = { task: string; rows: [string, string][]; retry?: boolean };

// /api/chat · /api/recovery(POST) · /api/waiting 의 답
export type Reply = {
  answer: string | null;
  pending: Pending | null;
  proposal: Proposal | null;
  notices?: string[];
  domain: Domain | null;
};

// 켤 때 남아 있던 진행 중 업무 (/api/recovery GET)
export type RecoveryRecord = { kind: string; request_text: string; when: string };

export const won = (n: number) => n.toLocaleString("ko-KR");
