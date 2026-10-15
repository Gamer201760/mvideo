import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { parseDuration } from "@/shared/motion/css-tokens"

const ROOT = process.cwd()
const TOKENS_DIR = resolve(ROOT, "src/shared/styles/tokens")
const motionCss = readFileSync(join(TOKENS_DIR, "motion.css"), "utf8")
const keyframesCss = readFileSync(join(TOKENS_DIR, "keyframes.css"), "utf8")
const RULE_DURATIONS: Readonly<Record<string, string>> = {
  "--dur-instant": "80ms",
  "--dur-press": "140ms",
  "--dur-fast": "160ms",
  "--dur-fast-exit": "110ms",
  "--dur-base": "200ms",
  "--dur-exit": "140ms",
  "--dur-panel": "260ms",
  "--dur-slow": "320ms",
  "--dur-draw": "900ms",
}

function declarations(block: string): Map<string, string> {
  return new Map(
    [...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [
      match[1] ?? "",
      (match[2] ?? "").trim(),
    ]),
  )
}

function stylesheets(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return stylesheets(path)
    return path.endsWith(".css") && !path.startsWith(TOKENS_DIR) ? [path] : []
  })
}

const reducedStart = motionCss.indexOf("@media (prefers-reduced-motion: reduce)")
const rootTokens = declarations(motionCss.slice(0, reducedStart))
const reducedBlock = motionCss.slice(reducedStart)
const reducedRoot = declarations(reducedBlock.slice(0, reducedBlock.indexOf("[data-motion")))
const durations = [...rootTokens.keys()].filter((token) => token.startsWith("--dur-"))
const durationOf = (token: string) => parseDuration(rootTokens.get(token) ?? "")

describe("motion tokens", () => {
  it("uses the curves and durations from the rules verbatim", () => {
    expect(rootTokens.get("--ease-out")).toBe("cubic-bezier(0.23, 1, 0.32, 1)")
    expect(rootTokens.get("--ease-in-out")).toBe("cubic-bezier(0.77, 0, 0.175, 1)")
    expect(rootTokens.get("--ease-drawer")).toBe("cubic-bezier(0.32, 0.72, 0, 1)")
    expect(rootTokens.has("--ease-in")).toBe(false)
    for (const [token, value] of Object.entries(RULE_DURATIONS))
      expect(rootTokens.get(token), token).toBe(value)
    expect(rootTokens.get("--stagger")).toBe("40ms")
    expect(rootTokens.get("--press-scale")).toBe("0.97")
    expect(rootTokens.get("--press-scale-surface")).toBe("0.99")
  })

  it("compresses every duration to 1ms under reduced motion", () => {
    for (const token of durations) expect(reducedRoot.get(token), token).toBe("1ms")
    expect(reducedRoot.get("--stagger")).toBe("0ms")
    expect(reducedRoot.get("--press-scale")).toBe("1")
    expect(reducedRoot.get("--enter-scale")).toBe("1")
    expect(reducedBlock).toContain('[data-motion="fade"]')
  })

  it("makes every exit faster than its entrance", () => {
    for (const token of durations.filter((name) => name.endsWith("-exit"))) {
      const entrance = token === "--dur-exit" ? "--dur-base" : token.replace(/-exit$/, "")
      expect(durationOf(token), token).toBeLessThan(durationOf(entrance))
    }
  })

  it("points every --motion-* at an existing keyframe", () => {
    const keyframes = new Set([...keyframesCss.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]))
    for (const [token, value] of [...rootTokens].filter(([name]) => name.startsWith("--motion-")))
      expect(keyframes.has(value.split(/\s+/)[0]), token).toBe(true)
  })

  it("keeps ms, cubic-bezier and !important out of styles outside tokens", () => {
    const offenders = stylesheets(resolve(ROOT, "src")).filter((path) =>
      /\d+m?s\b|cubic-bezier|!important/.test(readFileSync(path, "utf8")),
    )
    expect(offenders.map((path) => relative(ROOT, path))).toEqual([])
  })
})
