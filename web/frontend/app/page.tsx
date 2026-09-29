"use client";

// 첫 화면 : 왼쪽 메뉴 | 가운데 (총 잔액 + 계좌 + 대화) | 오른쪽 패널
// 메뉴 화면(계좌, 거래 내역 …)과 버튼 업무는 Next 전환 3단계에서 옮깁니다. 지금은 에이전트(대화)만 있습니다.
// 대화는 메뉴를 바꿔도 지워지지 않게 늘 그려 두고 숨기기만 합니다.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Chat from "@/components/Chat";
import SidePanel from "@/components/SidePanel";
import ThemeToggle from "@/components/ThemeToggle";
import { getJSON, postJSON } from "@/lib/api";
import type { Pending, Summary } from "@/lib/types";
import { won } from "@/lib/types";

const MENUS = [
  ["agent", "에이전트"], ["accounts", "계좌"], ["transactions", "거래 내역"], ["cards", "카드"],
  ["bills", "카드값"], ["schedules", "예약 이체"], ["requests", "처리 기록"],
] as const;
type View = (typeof MENUS)[number][0];

export default function Home() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [alerts, setAlerts] = useState<string[]>([]);
  const [view, setView] = useState<View>("agent");

  // 로그인 전이면 getJSON 이 로그인 화면으로 보냅니다.
  const loadSummary = useCallback(() => { getJSON<Summary>("/api/summary").then(setSummary); }, []);
  useEffect(loadSummary, [loadSummary]);

  // 예약 이체·분할 회차가 실행된 결과를 알림에 쌓습니다. (최근 것이 위, 5개까지)
  const addAlerts = useCallback((lines: string[]) => {
    if (lines.length) setAlerts((prev) => [...[...lines].reverse(), ...prev].slice(0, 5));
  }, []);

  async function logout() {
    await postJSON("/api/logout");
    router.replace("/login");
  }

  return (
    <div className="app-page">
      <div className="app">
        <aside className="side">
          <div className="brand">가상은행</div>
          {MENUS.map(([key, label]) => (
            <div key={key} className={"nav" + (view === key ? " on" : "")} onClick={() => setView(key)}>{label}</div>
          ))}
          <div className="me-box">
            <b>{summary?.user ?? "-"}</b><br />
            <span className="muted">{summary?.authenticated ? "본인 확인 완료" : "본인 확인 전"}</span>
            <div className="me-tools"><ThemeToggle /></div>
            <a onClick={logout}>로그아웃</a>
          </div>
        </aside>

        <main className="main">
          <div className="top">
            <div className="top-label">내 계좌 총 잔액</div>
            <div className="total"><span className="mono">{summary ? won(summary.total) : "-"}</span><small>원</small></div>
            <div className="accounts">
              {summary && (summary.accounts.length ? summary.accounts.map((a, i) => (
                <div key={i} className="acc"><div>{a.name}</div><div className="mono">{won(a.balance)}</div></div>
              )) : <div className="empty">계좌가 없어요</div>)}
            </div>
          </div>
          <div className="view-wrap" hidden={view !== "agent"}>
            <Chat userName={summary?.user ?? ""} onChanged={loadSummary} onPending={setPending} onAlerts={addAlerts} />
          </div>
          {view !== "agent" && (
            <section className="page-view">
              <div className="page-head"><h2>{MENUS.find(([key]) => key === view)?.[1]}</h2></div>
              <div className="empty">이 화면은 다음 단계에서 옮깁니다.</div>
            </section>
          )}
        </main>

        <SidePanel summary={summary} pending={pending} alerts={alerts} />
      </div>
    </div>
  );
}
