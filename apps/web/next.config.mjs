/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["@ai-rxos/ui", "@ai-rxos/sdk", "@ai-rxos/types"],
  experimental: {
    optimizePackageImports: ["@ai-rxos/ui"],
  },
};

export default nextConfig;
