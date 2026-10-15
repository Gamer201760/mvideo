import { mkdirSync } from "node:fs"
import { join, resolve } from "node:path"
import { type Browser, chromium, type Page } from "@playwright/test"
import { createServer, type ViteDevServer } from "vite"

type ShotState = "live" | "loading" | "error"

interface Options {
  readonly base: string | null
  readonly routes: readonly string[]
  readonly widths: readonly number[]
  readonly themes: readonly string[]
  readonly locales: readonly string[]
  readonly states: readonly ShotState[]
  readonly out: string
  readonly full: boolean
}

const HEIGHT = 900
const SETTLE_MS = 400
const SHOT_STATES: readonly ShotState[] = ["live", "loading", "error"]
const frontendRoot = resolve(import.meta.dirname, "..")

function option(name: string, fallback: string): string {
  const index = process.argv.indexOf(`--${name}`)
  return index === -1 ? fallback : (process.argv[index + 1] ?? fallback)
}

function list(name: string, fallback: string): string[] {
  return option(name, fallback)
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "")
}

function parse(): Options {
  const states = list("states", "live").filter((state): state is ShotState =>
    (SHOT_STATES as readonly string[]).includes(state),
  )
  return {
    base: process.argv.includes("--base") ? option("base", "") : null,
    routes: list("routes", "root").map(routePath),
    widths: list("widths", "375,768,1024,1440,1920").map(Number),
    themes: list("themes", "light,dark"),
    locales: list("locales", "ru,en"),
    states: states.length === 0 ? ["live"] : states,
    out: resolve(frontendRoot, option("out", "screenshots")),
    full: process.argv.includes("--full"),
  }
}

export function routePath(route: string): string {
  if (route === "root" || route === "/") return "/"
  return route.startsWith("/") ? route : `/${route}`
}

export function routeFolder(route: string): string {
  const name = route.replace(/^\/+|\/+$/g, "").replace(/[^\w-]+/g, "_")
  return name === "" ? "root" : name
}

const isApiRequest = (url: URL) => url.pathname.startsWith("/api/")

async function stage(page: Page, state: ShotState): Promise<void> {
  await page.unroute(isApiRequest)
  if (state === "error")
    await page.route(isApiRequest, (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ code: "server_unavailable" }),
      }),
    )
  if (state === "loading") await page.route(isApiRequest, () => new Promise<void>(() => undefined))
}

async function settle(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Number.POSITIVE_INFINITY)
      .every((animation) => animation.playState !== "running"),
  )
  await page.waitForTimeout(SETTLE_MS)
}

async function shootContext(
  browser: Browser,
  base: string,
  options: Options,
  [theme, locale]: readonly [string, string],
): Promise<void> {
  const context = await browser.newContext({ viewport: { width: 1440, height: HEIGHT } })
  await context.addInitScript(
    ([chosenTheme, chosenLocale]) => {
      localStorage.setItem("app-theme", chosenTheme ?? "light")
      localStorage.setItem("app-locale", chosenLocale ?? "ru")
    },
    [theme, locale],
  )
  const page = await context.newPage()
  for (const state of options.states) {
    await stage(page, state)
    for (const route of options.routes) {
      const folder = join(options.out, routeFolder(route))
      mkdirSync(folder, { recursive: true })
      for (const width of options.widths) {
        await page.setViewportSize({ width, height: HEIGHT })
        await page.goto(`${base}${route}`, { waitUntil: "load" })
        await settle(page)
        const suffix = state === "live" ? "" : `-${state}`
        const name = `${width}-${theme}-${locale}${suffix}.png`
        await page.screenshot({ path: join(folder, name), fullPage: options.full })
        process.stdout.write(`${routeFolder(route)}/${name}\n`)
      }
    }
  }
  await context.close()
}

async function startServer(): Promise<{ base: string; server: ViteDevServer }> {
  const server = await createServer({ root: frontendRoot, logLevel: "error" })
  await server.listen()
  const base = server.resolvedUrls?.local[0]?.replace(/\/$/, "")
  if (base === undefined) throw new Error("shots: dev server did not report its address")
  return { base, server }
}

const options = parse()
const started = options.base === null ? await startServer() : null
const base = options.base ?? started?.base ?? ""
const browser = await chromium.launch()
try {
  for (const theme of options.themes)
    for (const locale of options.locales)
      await shootContext(browser, base, options, [theme, locale])
} finally {
  await browser.close()
  await started?.server.close()
}
