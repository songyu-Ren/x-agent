import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
      {
        source: "/metrics",
        destination: `${backend}/metrics`,
      },
      {
        source: "/health",
        destination: `${backend}/health`,
      },
    ];
  },
};

export default nextConfig;
