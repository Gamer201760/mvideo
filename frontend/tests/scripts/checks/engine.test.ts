import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, relative, resolve, sep } from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import {
  compareWithBaseline,
  countByFile,
  formatBaseline,
  parseBaseline,
  prunedBaseline,
} from "../../../scripts/checks/baseline.ts"
import { collectFiles, frontendRoot, MissingSourcesError } from "../../../scripts/checks/files.ts"
import { CHECKS } from "../../../scripts/checks/registry.ts"

const CHECKS_DIR = resolve(process.cwd(), "scripts", "checks")
const RULES_DIR = join(CHECKS_DIR, "rules")
const EXPORTED_CHECK = /export const (\w+)(?:: Check = \{|\s*=\s*packageCheck\()/g
const roots: string[] = []

function tree(files: Readonly<Record<string, string>>): string {
  const root = mkdtempSync(join(tmpdir(), "checks-"))
  roots.push(root)
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true })
    writeFileSync(join(root, path), text)
  }
  return root
}

function ruleFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? ruleFiles(path) : [path]
  })
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe("ratchet baseline", () => {
  const baseline = parseBaseline("2\tsrc/a.ts\n5\tsrc/b.ts\n")

  it("round-trips through the text format", () => {
    expect(formatBaseline(baseline)).toBe("2\tsrc/a.ts\n5\tsrc/b.ts\n")
    expect(formatBaseline(new Map())).toBe("")
  })

  it("counts violations by file with weights", () => {
    const counts = countByFile([
      { file: "src/a.ts", message: "x" },
      { file: "src/a.ts", message: "y", weight: 3 },
    ])
    expect(counts.get("src/a.ts")).toBe(4)
  })

  it("fails new files and growth, accepts known violations", () => {
    const current = new Map([
      ["src/a.ts", 2],
      ["src/b.ts", 6],
      ["src/c.ts", 1],
    ])
    const { regressions } = compareWithBaseline(current, baseline)
    expect(regressions.map((item) => item.file)).toEqual(["src/b.ts", "src/c.ts"])
  })

  it("only shrinks when pruning", () => {
    const current = new Map([
      ["src/a.ts", 1],
      ["src/c.ts", 9],
    ])
    const { improvements } = compareWithBaseline(current, baseline)
    expect(improvements.map((item) => item.file)).toEqual(["src/a.ts", "src/b.ts"])
    expect([...prunedBaseline(current, baseline)]).toEqual([["src/a.ts", 1]])
  })
})

describe("registry", () => {
  it("registers every check exported from rules with a unique id", () => {
    const registry = readFileSync(join(CHECKS_DIR, "registry.ts"), "utf8")
    const list = registry.slice(registry.indexOf("CHECKS"))
    for (const path of ruleFiles(RULES_DIR)) {
      const specifier = `./${relative(CHECKS_DIR, path).split(sep).join("/")}`
      expect(registry, specifier).toContain(`"${specifier}"`)
      for (const match of readFileSync(path, "utf8").matchAll(EXPORTED_CHECK))
        expect(list, match[1]).toMatch(new RegExp(`\\b${match[1]},`))
    }
    const ids = CHECKS.map((check) => check.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe("collectFiles", () => {
  it("scans sources, tests, scripts and root configs, skipping dependencies", () => {
    const root = tree({
      "src/a.ts": "",
      "e2e/a.spec.ts": "",
      "public/favicon.svg": "",
      "index.html": "",
      Dockerfile: "",
      "nginx.conf": "",
      "vite.config.ts": "",
      "tsconfig.json": "",
      "node_modules/x/index.js": "",
      "src/.cache/state.json": "",
    })
    expect(collectFiles(root).map((item) => item.path)).toEqual([
      "Dockerfile",
      "e2e/a.spec.ts",
      "index.html",
      "nginx.conf",
      "src/a.ts",
      "tsconfig.json",
      "vite.config.ts",
    ])
  })

  it("fails instead of passing when there are no sources", () => {
    expect(() => collectFiles(tree({ "README.md": "" }))).toThrow(MissingSourcesError)
  })

  it("roots the checks at the frontend", () => {
    expect(frontendRoot(resolve(process.cwd(), "scripts", "checks"))).toBe(process.cwd())
  })
})
