"use client";

// 회원가입 화면. 적은 값을 /api/signup 에 보냅니다. 검사는 FastAPI 가 하고, 안 되면 사유를 보여줍니다.
// 가입되면 FastAPI 가 로그인 쿠키까지 주므로 바로 첫 화면(/)으로 갑니다. 이미 로그인돼 있으면 바로 첫 화면으로 보냅니다.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "@/components/ThemeToggle";

// 입력칸 : [보낼 이름, 보이는 이름, 입력칸 종류, 안내 글]
const FIELDS = [
  ["name", "이름", "text", ""],
  ["phone", "휴대전화번호", "text", "010-1234-5678"],
  ["login_id", "아이디", "text", "영어 소문자·숫자 4~20자"],
  ["password", "비밀번호", "password", "8자 이상"],
  ["pin", "PIN (본인 확인용 숫자 4자리)", "password", ""],
  ["ssn_tail", "주민등록번호 뒷자리 (본인 확인용 숫자 7자리)", "password", ""],
] as const;

type Key = (typeof FIELDS)[number][0];

export default function SignupPage() {
  const router = useRouter();
  const [values, setValues] = useState<Record<Key, string>>({
    name: "", phone: "", login_id: "", password: "", pin: "", ssn_tail: "",
  });
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    // 이미 로그인돼 있으면 첫 화면으로 (로그인 화면과 같음)
    fetch("/api/summary").then((res) => {
      if (res.ok) router.replace("/");
    });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError("");
    const res = await fetch("/api/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (res.ok) {
      router.replace("/");
      return;
    }
    setError((await res.json()).error || "가입하지 못했습니다.");
    setSending(false);
  }

  return (
    <main className="auth-page">
      <div className="auth-corner"><ThemeToggle /></div>
      <form className="auth-form" onSubmit={submit}>
        <h1>회원가입</h1>
        <p>계좌·카드 없이 시작합니다. 가입하면 바로 로그인됩니다.</p>
        {FIELDS.map(([key, label, type, placeholder]) => (
          <div key={key} style={{ display: "contents" }}>
            <label htmlFor={key}>{label}</label>
            <input id={key} type={type} placeholder={placeholder} required
                   maxLength={key === "pin" ? 4 : key === "ssn_tail" ? 7 : undefined}
                   inputMode={key === "pin" || key === "ssn_tail" ? "numeric" : undefined}
                   autoComplete={key === "password" ? "new-password" : key === "login_id" ? "username" : "off"}
                   value={values[key]} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
          </div>
        ))}
        {error && <div className="form-error">{error}</div>}
        <button type="submit" disabled={sending}>가입하기</button>
        <p className="switch">이미 아이디가 있으면 <Link href="/login">로그인</Link></p>
      </form>
    </main>
  );
}
