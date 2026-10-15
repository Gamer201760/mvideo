import { describe, expect, it } from "vitest"
import {
  buildTokenCss,
  contractGaps,
  GLOBAL_CONTRACT,
  pickFontFaces,
  THEMED_CONTRACT,
  tokenCss,
} from "../../scripts/exportTokens.ts"
import { metaValues } from "../../scripts/htmlMeta.ts"
import { readTokenSources, TOKEN_FILES, themeColor } from "../../scripts/tokenSources.ts"

const ROOT = process.cwd()
const sources = TOKEN_FILES.map((name) => ({
  name,
  text: `/* note */\n:root { --${name.replace(".css", "")}: 1; }`,
}))

describe("exportTokens", () => {
  it("joins token files in layer order without comments", () => {
    const css = buildTokenCss([...sources].reverse())
    expect(css.indexOf("--palette")).toBeLessThan(css.indexOf("--semantic"))
    expect(css.indexOf("--motion")).toBeLessThan(css.indexOf("--keyframes"))
    expect(css).not.toContain("/*")
  })

  it("fails when a token layer is missing", () => {
    expect(() => buildTokenCss(sources.slice(1))).toThrow(/palette\.css/)
  })

  it("emits both themes on plain attribute selectors for the deck", () => {
    const css = tokenCss(ROOT)
    expect(css).toMatch(/:root,\s*\[data-theme="light"\]\s*\{/)
    expect(css).toMatch(/(^|\n)\[data-theme="dark"\]\s*\{/)
    expect(css).not.toContain(":root[data-theme")
  })

  it("covers the deck contract and names the gaps", () => {
    expect(contractGaps(tokenCss(ROOT))).toEqual([])
    const bare = ':root { --font-sans: x; }\n:root,\n[data-theme="light"] { --surface-base: x; }'
    const gaps = contractGaps(bare)
    expect(gaps).toContain("--surface-raised (light)")
    expect(gaps).toContain("--surface-base (dark)")
    expect(gaps).not.toContain("--font-sans")
    expect(gaps).toHaveLength(THEMED_CONTRACT.length * 2 - 1 + GLOBAL_CONTRACT.length - 1)
  })

  it("keeps latin and cyrillic font faces with relative urls", () => {
    const css = [
      "/* inter-cyrillic-wght-normal */",
      "@font-face { src: url(./files/inter-cyrillic.woff2); }",
      "/* inter-greek-wght-normal */",
      "@font-face { src: url(./files/inter-greek.woff2); }",
    ].join("\n")
    const faces = pickFontFaces(css)
    expect(faces.files).toEqual(["inter-cyrillic.woff2"])
    expect(faces.css).toContain('url("fonts/inter-cyrillic.woff2")')
  })
})

describe("htmlMeta", () => {
  it("fills title, description and theme colors from dictionaries and tokens", () => {
    const values = metaValues(ROOT)
    const tokens = readTokenSources(ROOT)
    expect(values["%meta.title%"]).toMatch(/^.+ \| .+$/)
    expect(values["%meta.ogImage%"]).toMatch(/og\/og-ru\.png$/)
    expect(values["%meta.description%"]).not.toBe("")
    expect(values["%theme.light%"]).toBe(themeColor(tokens, "light", "--surface-base"))
    expect(values["%theme.dark%"]).toMatch(/^#[0-9a-f]{6}$/)
  })
})
