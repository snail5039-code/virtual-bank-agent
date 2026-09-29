"use client";

// 개인정보 화면 : 이름·휴대전화번호를 고치고, 로그인 비밀번호·본인 확인 PIN 을 바꿉니다. (/api/profile)
// 무엇을 바꾸든 지금 로그인 비밀번호를 한 번 넣어야 저장됩니다. 비밀번호·PIN 칸은 비워 두면 그대로입니다.
// 아이디와 주민번호 뒷자리는 바꿀 수 없어서 보여주기만 합니다(주민번호는 해시라 보여주지도 않음).

import { useEffect, useState } from "react";

type Profile = { name: string; phone: string; login_id: string | null };

export default function ProfilePage({ onChanged }: { onChanged: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPassword2, setNewPassword2] = useState("");
  const [newPin, setNewPin] = useState("");
  const [current, setCurrent] = useState("");
  const [result, setResult] = useState<{ text: string; ok: boolean } | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    // 401 이면 로그인 화면으로 가야 해서 lib/api 의 getJSON 과 같은 일을 합니다.
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
    // 새 비밀번호는 두 번 적게 해서 잘못 친 채로 바뀌지 않게 합니다. (화면에서만 비교)
    if (newPassword !== newPassword2) {
      setResult({ text: "새 비밀번호 두 칸이 서로 다릅니다.", ok: false });
      return;
    }
    setSending(true);
    // 틀린 값(400)도 사유를 보여줘야 해서 fetch 를 바로 씁니다.
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current, name, phone, new_password: newPassword, new_pin: newPin }),
    });
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    if (res.status === 401) { window.location.href = "/login"; return; }
    const data = await res.json();
    setSending(false);
    setCurrent("");      // 지금 비밀번호는 한 번 쓰고 비웁니다
    if (!res.ok) {
      setResult({ text: data.error, ok: false });
      return;
    }
    setResult({ text: data.answer, ok: true });
    setNewPassword("");
    setNewPassword2("");
    setNewPin("");
    onChanged();         // 왼쪽 이름·처리 기록을 새 값으로
  }

  return (
    <section className="page-view">
      <div className="page-head"><h2>개인정보</h2></div>
      {!profile ? <div className="empty">불러오는 중...</div> : (
        <form className="profile-form" onSubmit={save}>
          <div className="field"><span>아이디 (바꿀 수 없어요)</span><div className="mono">{profile.login_id ?? "-"}</div></div>
          <label className="field"><span>이름</span>
            <input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="field"><span>휴대전화번호</span>
            <input value={phone} placeholder="예: 010-1234-5678" onChange={(e) => setPhone(e.target.value)} /></label>

          <h3 className="sub-title">비밀번호 · PIN 바꾸기 <span className="muted">(비워 두면 그대로)</span></h3>
          <label className="field"><span>새 로그인 비밀번호 (8자 이상)</span>
            <input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} /></label>
          <label className="field"><span>새 로그인 비밀번호 확인</span>
            <input type="password" autoComplete="new-password" value={newPassword2} onChange={(e) => setNewPassword2(e.target.value)} /></label>
          <label className="field"><span>새 본인 확인 PIN (숫자 4자리)</span>
            <input type="password" inputMode="numeric" autoComplete="off" value={newPin} onChange={(e) => setNewPin(e.target.value)} /></label>

          <h3 className="sub-title">저장하기 전 확인</h3>
          <label className="field"><span>지금 로그인 비밀번호</span>
            <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
          {result && <div className={"modal-msg " + (result.ok ? "ok" : "bad")}>{result.text}</div>}
          <div className="actions"><button type="submit" className="primary" disabled={sending}>저장</button></div>
        </form>
      )}
    </section>
  );
}
