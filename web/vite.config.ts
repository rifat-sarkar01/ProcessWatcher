import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Run with the repository as the vitest root so `--run <path>` filters work with
    // repo-relative paths, which is how 06_Plan.md writes every FE Done-when command.
    root: "..",
    setupFiles: ["./web/src/test-setup.ts"],
    css: true,
    include: ["web/src/**/*.{test,spec}.{ts,tsx}"],
  },
});
