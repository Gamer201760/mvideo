import { describe, expect, it } from "vitest"
import { noGradients } from "../../../scripts/checks/rules/css/decor.ts"
import { pageWidth } from "../../../scripts/checks/rules/css/pageWidth.ts"
import { scaleTokens, tokenLayers } from "../../../scripts/checks/rules/css/scale.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text: string): SourceFile => ({ path, text })
const tokens = (name: string, text: string) => file(`src/shared/styles/tokens/${name}`, text)
const module = (css: string) => file("src/shared/ui/box/styles.module.css", css)
const PALETTE = tokens("palette.css", ":root { --neutral-0: #ffffff; --accent-500: #3d5bd9; }")
const SPACE = (prose = "70ch", field = "480px") =>
  tokens("space.css", `:root { --prose-measure: ${prose}; --field-max-width: ${field}; }`)

describe("scale-tokens", () => {
  it("accepts scale tokens, also through local component properties", () => {
    const css =
      ".box { --box-radius: var(--radius-lg); border-radius: var(--box-radius) var(--radius-lg) 0 0; font-size: var(--font-size-body); z-index: var(--layer-popover); box-shadow: var(--shadow-float); padding: var(--space-4) calc(var(--space-12) - var(--hairline)); margin: 0 auto; } @media (min-width: 48rem) { .box { gap: 0; } }"
    expect(scaleTokens.run([module(css)])).toEqual([])
  })

  it.each([
    "border-radius: var(--space-4);",
    "box-shadow: 0 1px 2px var(--surface-raised);",
    "font-size: var(--size);",
    "font: 600 13px/1.1 var(--font-sans);",
    "z-index: 3;",
    "padding: 13px 7px;",
    "gap: 0.5rem;",
  ])("reports %s", (declaration) => {
    expect(scaleTokens.run([module(`.box { ${declaration} }`)])).toHaveLength(1)
  })

  it("reports breakpoints outside the scale in media queries and matchMedia", () => {
    const css = "@media (min-width: 860px) { .box { gap: 0; } }"
    const script = file("src/features/x/media.ts", 'matchMedia("(max-width: 900px)")\n')
    expect(scaleTokens.run([module(css), script])).toHaveLength(2)
  })
})

describe("token-layers", () => {
  it("allows semantic tokens and reports palette tokens, also behind an alias", () => {
    expect(tokenLayers.run([PALETTE, module(".box { color: var(--text-primary); }")])).toEqual([])
    const aliased = module(".box { --box-ink: var(--accent-500); color: var(--box-ink); }")
    expect(tokenLayers.run([PALETTE, aliased]).length).toBeGreaterThan(0)
  })
})

describe("no-gradients", () => {
  it("allows masks and reports gradients and gradient text", () => {
    const css =
      ".a { mask-image: linear-gradient(var(--a), transparent); }\n.b { background: linear-gradient(var(--a), var(--b)); }\n.c { background-clip: text; }"
    expect(noGradients.run([module(css)]).map((item) => item.message)).toEqual([
      expect.stringContaining("gradient: background"),
      expect.stringContaining("gradient text"),
    ])
  })
})

describe("page-width", () => {
  it("allows prose and field measures, 100% and none", () => {
    const css =
      ".a { max-inline-size: var(--prose-measure); }\n.b { max-width: var(--field-max-width); }\n.c { max-width: 100%; }\n.d { max-inline-size: none; }"
    expect(pageWidth.run([SPACE(), module(css)])).toEqual([])
  })

  it("reports a page column and measures above the limits", () => {
    const css =
      ".page { max-width: 1200px; margin-inline: auto; }\n.b { max-width: var(--page-max); }"
    expect(pageWidth.run([SPACE(), module(css)])).toHaveLength(2)
    expect(pageWidth.run([SPACE("90ch", "640px")])).toHaveLength(2)
  })
})
