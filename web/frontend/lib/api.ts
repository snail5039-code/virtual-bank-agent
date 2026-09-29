// FastAPI(/api/...) 로 보내는 요청을 한 곳에 모았습니다.
// 들어온 상태가 풀리면(서버를 다시 켰을 때 등) FastAPI 가 401 을 돌려주므로, 그때는 첫 화면(계정 고르기, /login)으로 보냅니다.
// 계정 고르기 화면은 틀린 값의 사유(400·404)를 보여줘야 해서 이 함수 대신 fetch 를 바로 씁니다.

async function send<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (res.status === 401) {
    // 컴포넌트 밖이라 router 를 못 씁니다. 화면을 통째로 새로 여는 것이 들어오기 전 상태를 깨끗이 비우기도 합니다.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
    // 계정 고르기 화면으로 넘어가는 중이라 부른 쪽이 이어서 할 일이 없습니다. 끝나지 않는 약속을 돌려줘 멈춰 둡니다.
    return new Promise<T>(() => {});
  }
  return res.json();
}

export function getJSON<T>(url: string): Promise<T> {
  return send<T>(url);
}

export function postJSON<T>(url: string, body?: unknown): Promise<T> {
  return send<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}
