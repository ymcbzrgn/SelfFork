/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export ONLY in production builds. `next dev` runs in SSR
  // mode so dynamic routes (`/workspaces/[slug]`) render on demand
  // against the orchestrator — required because workspace slugs are
  // user-created at runtime and not known at build time.
  //
  // `next build && next export` (production) reads the project list
  // at build time via `generateStaticParams` in
  // `app/workspaces/[slug]/page.tsx` and pre-renders one HTML shell
  // per known workspace; new workspaces created post-deploy require
  // a rebuild (acceptable for a self-hosted single-operator app).
  ...(process.env.NODE_ENV === "production" ? { output: "export" } : {}),
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
