import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:5000";
const isDev = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  basePath: '/scanner',
  // Hide the Next.js "N" / Node dev badge (bottom-left).
  devIndicators: {
    appIsrStatus: false,
    buildActivity: false,
  },
  async redirects() {
    return [
      {
        source: "/",
        destination: "/scanner",
        permanent: false,
        basePath: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        // Keep Next-owned routes off the Flask proxy.
        source: "/api/:path((?!demo|captcha|auth|me).*)",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    if (isDev) return [];

    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-DNS-Prefetch-Control", value: "on" },
        ],
      },
    ];
  },
};

export default nextConfig;
