import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const read = (path: string): string => readFileSync(resolve(process.cwd(), path), "utf8")
const json = (path: string): Record<string, unknown> =>
  JSON.parse(read(path)) as Record<string, unknown>

describe("tooling", () => {
  it("keeps TypeScript strict with the flags from the rules", () => {
    const options = json("tsconfig.json").compilerOptions as Record<string, unknown>
    for (const flag of [
      "strict",
      "noUncheckedIndexedAccess",
      "exactOptionalPropertyTypes",
      "verbatimModuleSyntax",
    ])
      expect(options[flag], flag).toBe(true)
    expect((options.paths as Record<string, string[]>)["@/*"]).toEqual(["./src/*"])
  })

  it("runs every gate in verify", () => {
    const scripts = json("package.json").scripts as Record<string, string>
    expect(scripts.verify).toBe(
      "npm run rules && npm run typecheck && npm run lint && npm run test && npm run build",
    )
  })

  it("keeps the Biome rules and formatting from the rules", () => {
    const biome = json("biome.json")
    const formatter = biome.formatter as Record<string, unknown>
    expect([formatter.indentWidth, formatter.lineWidth, formatter.lineEnding]).toEqual([
      2,
      100,
      "lf",
    ])
    const javascript = (biome.javascript as Record<string, Record<string, unknown>>).formatter
    expect([javascript?.quoteStyle, javascript?.semicolons]).toEqual(["double", "asNeeded"])
    const rules = (biome.linter as Record<string, Record<string, Record<string, unknown>>>).rules
    expect(rules?.style?.noDefaultExport).toBe("error")
    expect(rules?.style?.noNonNullAssertion).toBe("error")
    expect(rules?.style?.useImportType).toBe("error")
    expect(rules?.suspicious?.noExplicitAny).toBe("error")
    const complexity = rules?.complexity?.noExcessiveCognitiveComplexity as {
      options: { maxAllowedComplexity: number }
    }
    expect(complexity.options.maxAllowedComplexity).toBe(15)
  })

  it("sets theme and language in index.html with the keys the app stores", () => {
    const html = read("index.html")
    const theme = /THEME_STORAGE_KEY = "([\w-]+)"/.exec(read("src/shared/theme/theme.ts"))?.[1]
    const locale = /LOCALE_STORAGE_KEY = "([\w-]+)"/.exec(read("src/shared/i18n/locale.ts"))?.[1]
    expect(html).toContain(`localStorage.getItem("${theme}")`)
    expect(html).toContain(`localStorage.getItem("${locale}")`)
    expect(html.indexOf("dataset.theme")).toBeLessThan(html.indexOf("/src/main.tsx"))
  })

  it("proxies the API in nginx through a resolver so the container starts alone", () => {
    const nginx = read("nginx.conf")
    expect(nginx).toContain("resolver 127.0.0.11")
    expect(nginx).toMatch(/proxy_pass \$\w+;/)
    expect(nginx).toContain("try_files $uri /index.html")
  })
})
