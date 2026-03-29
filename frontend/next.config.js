/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "*.s3.amazonaws.com" },
      { protocol: "https", hostname: "*.railway.app" },
      { protocol: "http", hostname: "localhost" },
    ],
  },
  // NEXT_PUBLIC_API_URL is set in Vercel → Project Settings → Environment Variables
  // pointing to your Railway backend URL (e.g. https://segmentiq-backend.railway.app)
};

module.exports = nextConfig;
