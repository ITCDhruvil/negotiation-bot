/** @type {import('next').NextConfig} */
const nextConfig = {
  // standalone is for Docker/on-prem; Vercel builds Next normally.
  output: process.env.VERCEL ? undefined : "standalone",
  async rewrites() {
    // On Vercel, vercel.json routes /backend to the FastAPI service.
    if (process.env.VERCEL) return [];
    const port = process.env.BACKEND_PORT || "8000";
    const backend = process.env.BACKEND_INTERNAL_URL || `http://127.0.0.1:${port}`;
    return [
      {
        source: "/backend/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
