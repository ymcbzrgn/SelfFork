/**
 * Vitest config for the SelfFork cockpit — Order 5.
 *
 * Uses the Vite React plugin so .tsx components compile in tests, plus
 * jsdom so React Testing Library has a DOM. Tests live alongside the
 * code under ``__tests__`` to keep the import paths short.
 */
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["__tests__/**/*.test.{ts,tsx}", "**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next", "out"],
  },
});
