/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // APIプロキシ設定（バックエンドへの通信用）
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://backend:8000/api/:path*',
      },
      {
        source: '/ws/:path*',
        destination: 'http://backend:8000/ws/:path*',
      },
    ];
  },
};
module.exports = nextConfig;
