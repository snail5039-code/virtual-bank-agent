"use client";

// 개인정보 화면 : 이름·휴대전화번호를 고치고, 본인 확인 PIN 을 바꿉니다. (/api/profile)
// 무엇을 바꾸든 지금 PIN 을 한 번 넣어야 저장됩니다. 새 PIN 칸은 비워 두면 그대로입니다.
// 휴대전화번호는 비워 둘 수 있습니다 (새 계정은 없이 시작). 넣어 두면 본인 확인에도 쓸 수 있습니다.

import { useEffect, useState } from "react";

type Profile = { name: string; phone: string };

export default function ProfilePage({ onChanged }: { onChanged: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [newPin, setNewPin] = useState("");
  const [newPin2, setNewPin2] = useState("");
  const [current, setCurrent] = useState("");
  const [result, setResult] = useState<{ text: string; ok: boolean } | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    // 401 이면 첫 화면(계정 고르기)으로 가야 해서 lib/api 의 getJSON 과 같은 일을 합니다.
    fetch("/api/profile").then(async (res) => {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      if (res.status === 401) { window.location.href = "/login"; return; }
      const p: Profile = await res.json();
      setProfile(p);
      setName(p.name);
      setPhone(p.phone);
    });
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    // 새 PIN 은 두 번 적게 해서 잘못 친 채로 바뀌지 않게 합니다. (화면에서만 비교)
    if (newPin !== newPin2) {
      setResult({ text: "새 PIN 두 칸이 서로 다릅니다.", ok: false });
      return;
    }
    setSending(true);
    // 틀린 값(400)도 사유를 보여줘야 해서 fetch 를 바로 씁니다.
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_pin: current, name, phone, new_pin: newPin }),
    });
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (res.status === 401) { window.location.href = "/login"; return; }
    const data = await res.json();
    setSending(false);
    setCurrent("");      // 지금 PIN 은 한 번 쓰고 비웁니다
    if (!res.ok) {
      setResult({ text: data.error, ok: false });
      return;
    }
    setResult({ text: data.answer, ok: true });
    setNewPin("");
    setNewPin2("");
    onChanged();         // 왼쪽 이름·처리 기록을 새 값으로
  }

  return (
    <section className="page-view">
      <div className="page-head"><h2>개인정보</h2></div>
      {!profile ? <div className="empty">불러오는 중...</div> : (
        <form className="profile-form" onSubmit={save}>
          <label className="field"><span>이름</span>
            <input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="field"><span>휴대전화번호 (없으면 비워 두세요)</span>
            <input value={phone} placeholder="예: 010-1234-5678" onChange={(e) => setPhone(e.target.value)} /></label>

          <h3 className="sub-title">PIN 바꾸기 <span className="muted">(비워 두면 그대로)</span></h3>
          <label className="field"><span>새 PIN (숫자 4자리)</span>
            <input type="password" inputMode="numeric" autoComplete="off" value={newPin} onChange={(e) => setNewPin(e.target.value)} /></label>
          <label className="field"><span>새 PIN 확인</span>
            <input type="password" inputMode="numeric" autoComplete="off" value={newPin2} onChange={(e) => setNewPin2(e.target.value)} /></label>

          <h3 className="sub-title">저장하기 전 확인</h3>
          <label className="field"><span>지금 PIN</span>
            <input type="password" inputMode="numeric" autoComplete="off" required value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
          {result && <div className={"modal-msg " + (result.ok ? "ok" : "bad")}>{result.text}</div>}
          <div className="actions"><button type="submit" className="primary" disabled={sending}>저장</button></div>
        </form>
      )}
    </section>
  );
}
