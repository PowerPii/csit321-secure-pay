/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The page is served at https://gateway.localhost/pay/cs_... (Caddy, deploy/Caddyfile) and
// calls the gateway's /checkout/* API on the same origin.
export default defineConfig({
  base: "/pay/",
  plugins: [react()],
  build: { sourcemap: false },
  server: {
    // `npm run dev`, then open http://localhost:5173/pay/cs_...; API calls go to runserver.
    proxy: { "/checkout": "http://localhost:8000" },
  },
  test: { environment: "jsdom" },
});
