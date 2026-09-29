import type { NextConfig } from "next";

// 화면(이 Next 앱)과 에이전트·데이터(FastAPI, web/server.py)를 나눠서 돌립니다.
// 화면에서 /api/... 로 보내면 Next 가 FastAPI 로 넘겨 줍니다. 주소창은 이 앱 주소 그대로라
// FastAPI 가 준 로그인 쿠키도 이 앱 주소로 저장되고, 다음 요청에 그대로 따라갑니다.
const API_SERVER = process.env.API_SERVER ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_SERVER}/api/:path*` }];
  },
  experimental: {
    // 에이전트 답은 LLM 을 여러 번 불러 기본값(30초)을 넘길 수 있어서 5분으로 늘립니다.
    proxyTimeout: 300_000,
  },
};

export default nextConfig;
