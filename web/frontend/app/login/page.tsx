"use client";

// 로그인 화면. 아이디·비밀번호를 /api/login 에 보내고, 맞으면 FastAPI 가 준 쿠키를 가지고 첫 화면(/)으로 갑니다.
// 이미 로그인돼 있으면 바로 첫 화면으로 보냅니다.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";

export default function LoginPage() {
  const router = useRouter();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch("/api/summary").then((res) => {
      if (res.ok) router.replace("/");
    });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_id: loginId, password }),
    });
    if (res.ok) {
      router.replace("/");
      return;
    }
    setError((await res.json()).error || "로그인하지 못했습니다.");
    setPassword("");
    setSending(false);
  }

  return (
    <main className="auth-page">
      <div className="auth-corner"><ThemeToggle /></div>
      <form className="auth-form" onSubmit={submit}>
        <h1>가상은행</h1>
        <p>로그인하고 이용하세요</p>
        <label htmlFor="login_id">아이디</label>
        <input id="login_id" autoComplete="username" required autoFocus value={loginId} onChange={(e) => setLoginId(e.target.value)} />
        <label htmlFor="password">비밀번호</label>
        <input id="password" type="password" autoComplete="current-password" required value={password}
               onChange={(e) => setPassword(e.target.value)} />
        {error && <div className="form-error">{error}</div>}
        <button type="submit" disabled={sending}>로그인</button>
        <p className="switch">처음이면 <Link href="/signup">회원가입</Link></p>
      </form>
    </main>
  );
}
