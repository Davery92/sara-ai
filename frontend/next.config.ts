import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        hostname: 'avatar.vercel.sh',
      },
    ],
  },
  // Allow cross-origin requests during development
  allowedDevOrigins: ['localhost', '10.185.1.38'],
};

export default nextConfig;
