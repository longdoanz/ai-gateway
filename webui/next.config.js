/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  basePath: "/webui",
  async rewrites() {
    const backendUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
        basePath: false,
      },
      {
        source: "/oauth/:path*",
        destination: `${backendUrl}/oauth/:path*`,
        basePath: false,
      },
      {
        source: "/.well-known/:path*",
        destination: `${backendUrl}/.well-known/:path*`,
        basePath: false,
      },
      {
        source: "/9router/:path*",
        destination: `${backendUrl}/9router/:path*`,
        basePath: false,
      },
    ];
  },
};

module.exports = nextConfig;
