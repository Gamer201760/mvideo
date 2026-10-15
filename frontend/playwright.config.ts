import { defineConfig, devices } from "@playwright/test"

const PORT = 5179
const external = process.env.E2E_BASE_URL
const baseURL = external ?? `http://localhost:${PORT}`
const webServer = {
  command: `npm run dev -- --port ${PORT} --strictPort`,
  url: baseURL,
  reuseExistingServer: true,
}

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  ...(external === undefined ? { webServer } : {}),
})
