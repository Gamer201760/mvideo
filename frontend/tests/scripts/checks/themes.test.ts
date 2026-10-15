import { describe, expect, it } from "vitest"
import { contrast, themeParity } from "../../../scripts/checks/rules/css/themeTokens.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const tokens = (name: string, text: string): SourceFile => ({
  path: `src/shared/styles/tokens/${name}`,
  text,
})
const PALETTE = tokens(
  "palette.css",
  ":root { --white: #ffffff; --ink: #1a1a1e; --mist: #f6f6f7; --grey: #ececee; --blue: #3d5bd9; --light: #93a6f2; --night: #121215; --pale: #b4b4bc; }",
)
const LIGHT = `--surface-base: var(--mist); --surface-raised: var(--white); --surface-raised-hover: color-mix(in oklab, var(--white), var(--ink) 4%); --surface-sunken: var(--grey); --surface-selected: var(--white); --text-primary: var(--ink); --text-disabled: var(--pale); --action-primary-text: var(--white); --action-primary: var(--blue); --action-primary-hover: var(--blue); --action-primary-press: var(--blue); --focus-ring: var(--blue);`
const DARK = `--surface-base: var(--night); --surface-raised: var(--ink); --surface-raised-hover: var(--ink); --surface-sunken: var(--ink); --surface-selected: var(--ink); --text-primary: var(--mist); --text-disabled: var(--pale); --action-primary-text: var(--night); --action-primary: var(--light); --action-primary-hover: var(--light); --action-primary-press: var(--light); --focus-ring: var(--light);`
const semantic = (light: string, dark: string) =>
  tokens(
    "semantic.css",
    `:root,\n:root[data-theme="light"] { ${light} }\n:root[data-theme="dark"] { ${dark} }`,
  )

describe("theme-parity", () => {
  it("passes a semantic layer defined in both themes", () => {
    expect(themeParity.run([PALETTE, semantic(LIGHT, DARK)])).toEqual([])
  })

  it("reports a token missing in one theme", () => {
    const messages = themeParity
      .run([PALETTE, semantic(`${LIGHT} --text-extra: var(--ink);`, DARK)])
      .map((item) => item.message)
    expect(messages).toEqual(["--text-extra has no dark value"])
  })

  it("reports theme selectors outside semantic.css and in components", () => {
    const files = [
      semantic(LIGHT, DARK),
      tokens("elevation.css", ':root[data-theme="dark"] { --shadow: none; }'),
      { path: "src/features/x/x.module.css", text: ':root[data-theme="dark"] .x { color: red; }' },
      { path: "src/features/x/x.ts", text: "const dark = root.dataset.theme\n" },
      { path: "src/shared/theme/theme.ts", text: "root.dataset.theme = theme\n" },
    ]
    expect(themeParity.run(files).map((item) => item.file)).toEqual([
      "src/shared/styles/tokens/elevation.css",
      "src/features/x/x.module.css",
      "src/features/x/x.ts",
    ])
  })
})

describe("contrast", () => {
  it("passes readable pairs in both themes", () => {
    expect(contrast.run([PALETTE, semantic(LIGHT, DARK)])).toEqual([])
  })

  it("reports a text token below 4.5:1 and an unresolved pair", () => {
    const weak = `${LIGHT} --text-secondary: var(--pale);`
    const messages = contrast
      .run([PALETTE, semantic(weak, `${DARK} --text-secondary: var(--pale);`)])
      .map((item) => item.message)
    expect(messages.some((message) => message.startsWith("light: --text-secondary"))).toBe(true)
    const broken = contrast.run([
      PALETTE,
      semantic(LIGHT.replace("--action-primary-text", "--x"), DARK),
    ])
    expect(broken.map((item) => item.message)).toContain(
      "light: cannot resolve --action-primary-text on --action-primary",
    )
  })
})
