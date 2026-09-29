"use client";

// 화면 색 고르기 : 자동(컴퓨터 설정을 따름) / 라이트 / 다크
// 고른 값은 브라우저(localStorage)에 남겨 다음에 열어도 그대로입니다.
// 실제 색은 globals.css 가 <html data-theme="light|dark"> 를 보고 바꿉니다. (자동이면 data-theme 을 뺌)
// 화면이 처음 그려지기 전에 칠해 두는 일은 layout.tsx 의 THEME_SCRIPT 가 합니다. (깜빡임 방지)

import { useEffect, useState } from "react";

type Theme = "auto" | "light" | "dark";
const LABELS: Record<Theme, string> = { auto: "자동", light: "라이트", dark: "다크" };
const KEY = "theme";

export function applyTheme(theme: Theme) {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  try {
    if (theme === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // 브라우저가 저장을 막아 두었으면 이번 화면에만 적용합니다.
  }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("auto");

  useEffect(() => {
    // 저장해 둔 값을 읽어 버튼 표시를 맞춥니다. (색은 THEME_SCRIPT 가 이미 칠해 둠)
    try {
      const saved = localStorage.getItem(KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 처음 한 번 저장값을 읽어 오는 것
      if (saved === "light" || saved === "dark") setTheme(saved);
    } catch {}
  }, []);

  const choose = (next: Theme) => {
    setTheme(next);
    applyTheme(next);
  };

  return (
    <div className="theme-toggle" role="group" aria-label="화면 색">
      {(Object.keys(LABELS) as Theme[]).map((t) => (
        <button key={t} type="button" className={t === theme ? "on" : ""} onClick={() => choose(t)}>
          {LABELS[t]}
        </button>
      ))}
    </div>
  );
}
