"use client";

// 첫 화면. (Next 전환 1단계 : 로그인 확인·로그아웃·화면 색만. 대화·메뉴는 2~3단계에서 옮깁니다)

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { getJSON, postJSON } from "@/lib/api";

type Summary = { user: string; total: number };

export default function Home() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    getJSON<Summary>("/api/summary").then(setSummary);     // 로그인 전이면 getJSON 이 로그인 화면으로 보냅니다
  }, []);

  async function logout() {
    await postJSON("/api/logout");
    router.replace("/login");
  }

  return (
    <main className="auth-page">
      <div className="auth-corner"><ThemeToggle /></div>
      <div className="auth-form">
        <h1>{summary ? summary.user + " 님" : "불러오는 중"}</h1>
        <p>총 잔액 <span className="mono">{summary ? summary.total.toLocaleString("ko-KR") : "-"}</span>원</p>
        <p>대화·메뉴 화면은 다음 단계에서 옮깁니다.</p>
        <button type="button" style={{ padding: "10px 12px" }} onClick={logout}>로그아웃</button>
      </div>
    </main>
  );
}
