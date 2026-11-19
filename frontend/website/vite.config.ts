/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
  // `npm test`: the public-site journey in src/journey.test.tsx (jsdom, no browser download).
  test: { environment: "jsdom", testTimeout: 15_000 },
});
