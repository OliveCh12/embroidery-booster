import type { NextConfig } from "next";

const api = (process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const config: NextConfig = {
  poweredByHeader: false,
  devIndicators: false,
  experimental: { proxyClientMaxBodySize: "12mb", proxyTimeout: 180_000 },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/quality-assets/:path*", destination: `${api}/quality/:path*` },
    ];
  },
};

export default config;
