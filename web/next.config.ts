import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  allowedDevOrigins: ["127.0.0.1", "panshi.localhost"],
  experimental: {
    middlewareClientMaxBodySize: "52mb"
  }
};

export default nextConfig;
