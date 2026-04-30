/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  basePath: "/webui",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
