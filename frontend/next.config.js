/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
  async rewrites() {
    const backendOrigin =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";

    return [
      {
        source: "/api/backend/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

const { withSentryConfig } = require("@sentry/nextjs");

module.exports = withSentryConfig(
  nextConfig,
  {
    silent: true,
  },
  {
    hideSourceMaps: true,
    disableLogger: true,
  },
);
