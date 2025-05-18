/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // Allow production builds to successfully complete even if there are type errors.
    ignoreBuildErrors: true,
  },
};

module.exports = nextConfig; 