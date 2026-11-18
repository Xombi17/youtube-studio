import type { NextConfig } from "next";

const STUDIO_API_URL = process.env.STUDIO_API_URL || "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${STUDIO_API_URL}/api/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${STUDIO_API_URL}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
