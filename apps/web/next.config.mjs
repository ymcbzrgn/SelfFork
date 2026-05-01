/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export so the FastAPI backend can serve the bundle from one
  // process. ``selffork ui`` mounts apps/web/out at /. Static export
  // disallows runtime rewrites — dev proxying happens via the
  // ``NEXT_PUBLIC_API_BASE_URL`` env var (set in ``.env.development``)
  // pointing fetch() at the FastAPI dev port (default 8765). Production
  // builds leave it empty (same-origin).
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
