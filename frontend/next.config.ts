import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 배포: 정적 파일(out/)로 내보내 a1.scnuoss.net 의 /home/a1/html/ 에 업로드
  output: "export",
  turbopack: { root: process.cwd() },
};

export default nextConfig;
