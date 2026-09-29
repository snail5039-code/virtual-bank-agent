"use client";

// 첫 화면 : 계정 고르기. 가상 은행이라 비밀번호 없이 계정을 눌러 바로 들어갑니다.
// 돈·상태가 바뀌는 업무는 들어온 뒤 본인 확인(PIN 등)을 따로 거칩니다.
//   왼쪽 : 있는 계정 (/api/users) → 누르면 /api/enter 로 들어가고 FastAPI 가 준 쿠키를 가지고 첫 화면(/)으로
//   오른쪽 : 새 계정 만들기 (이름 · PIN) → 만들고 바로 들어갑니다
// 이미 들어와 있으면 바로 첫 화면으로 보냅니다.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { won } from "@/lib/types";

type User = { id: string; name: string; accounts: number; total: number };

export default function PickAccountPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[] | null>(null);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetch("/api/summary").then((res) => {
      if (res.ok) router.replace("/");
    });
    fetch("/api/users").then((res) => res.json()).then(setUsers);
  }, [router]);

  async function enter(id: string) {
    setSending(true);
    const res = await fetch("/api/enter", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }),
    });
    if (res.ok) { router.replace("/"); return; }
    setError((await res.json()).error || "들어가지 못했습니다.");
    setSending(false);
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    const res = await fetch("/api/users", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, pin }),
    });
    if (res.ok) { router.replace("/"); return; }
    setError((await res.json()).error || "만들지 못했습니다.");
    setPin("");
    setSending(false);
  }

  return (
    <main className="auth-page">
      <div className="auth-corner"><ThemeToggle /></div>
      <div className="pick-page">
        <section className="pick-users">
          <h1>가상은행</h1>
          <p className="muted">들어갈 계정을 고르세요. 돈이 바뀌는 업무는 들어간 뒤 PIN 으로 본인 확인을 해요.</p>
          {!users ? <div className="empty">불러오는 중...</div> : (
            <div className="user-list">
              {users.map((u) => (
                <button key={u.id} type="button" className="user-card" disabled={sending} onClick={() => enter(u.id)}>
                  <span className="avatar user-avatar">{u.name.slice(0, 1)}</span>
                  <span className="user-name">{u.name}</span>
                  <span className="sub">{u.accounts ? "계좌 " + u.accounts + "개 · " : "계좌 없음"}
                    {u.accounts > 0 && <span className="mono">{won(u.total)}원</span>}</span>
                </button>
              ))}
            </div>
          )}
        </section>
        <form className="auth-form" onSubmit={create}>
          <h1>새 계정</h1>
          <p>이름과 본인 확인용 PIN 만 정하면 돼요</p>
          <label htmlFor="new_name">이름</label>
          <input id="new_name" required autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
          <label htmlFor="new_pin">PIN (숫자 4자리)</label>
          <input id="new_pin" type="password" inputMode="numeric" required autoComplete="off" value={pin}
                 onChange={(e) => setPin(e.target.value)} />
          {error && <div className="form-error">{error}</div>}
          <button type="submit" disabled={sending}>만들고 들어가기</button>
        </form>
      </div>
    </main>
  );
}
