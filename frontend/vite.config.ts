import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"
import { htmlMeta } from "./scripts/htmlMeta.ts"

const apiUrl = process.env.API_URL ?? "http://localhost:8000"
const frontendRoot = fileURLToPath(new URL(".", import.meta.url))
const sourceRoot = fileURLToPath(new URL("./src", import.meta.url))
const apiProxy = { "/api": { target: apiUrl, changeOrigin: true } }

export default defineConfig({
  plugins: [react(), htmlMeta(frontendRoot)],
  resolve: { alias: { "@": sourceRoot } },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  test: {
    css: { modules: { classNameStrategy: "non-scoped" } },
    projects: [
      {
        extends: true,
        test: { name: "node", environment: "node", include: ["tests/**/*.test.ts"] },
      },
      {
        extends: true,
        test: {
          name: "dom",
          environment: "jsdom",
          include: ["tests/**/*.test.tsx"],
          setupFiles: ["tests/setup/polyfills.ts", "tests/setup/dom.ts"],
        },
      },
    ],
  },
})
