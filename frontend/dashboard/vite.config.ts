/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served at https://gateway.localhost/dashboard/ (Caddy, deploy/Caddyfile); calls the
// gateway's staff API at /internal/* on the same origin with the session cookie.
export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  build: { sourcemap: false },
  server: {
    // `npm run dev`, then open http://localhost:5174/dashboard/; API calls go to runserver.
    proxy: { "/internal": "http://localhost:8000" },
  },
  test: { environment: "jsdom" },
});
