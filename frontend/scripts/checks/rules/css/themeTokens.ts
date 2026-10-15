import { ratioOf } from "../../color.ts"
import {
  resolveName,
  scopeOf,
  type ThemeName,
  type ThemeTables,
  themeTables,
} from "../../themes.ts"
import {
  type Check,
  componentStyles,
  type SourceFile,
  sourceScripts,
  TOKENS_DIR,
  type Violation,
} from "../../types.ts"

export const MIN_CONTRAST = 4.5
export const MIN_NON_TEXT_CONTRAST = 3
export const SEMANTIC_FILE = `${TOKENS_DIR}semantic.css`
export const THEME_OWNER = "src/shared/theme/"
export const TEXT_SURFACES = [
  "--surface-base",
  "--surface-raised",
  "--surface-raised-hover",
  "--surface-sunken",
]
export const ON_SURFACES: Readonly<Record<string, readonly string[]>> = {
  "--action-primary-text": ["--action-primary", "--action-primary-hover", "--action-primary-press"],
}
export const EXTRA_TEXT: ReadonlyArray<readonly [string, string]> = [
  ["--text-primary", "--surface-selected"],
]
export const EXEMPT_TEXT = new Set(["--text-disabled"])
const NON_TEXT: ReadonlyArray<readonly [string, string]> = [
  ["--focus-ring", "--surface-base"],
  ["--focus-ring", "--surface-raised"],
]
const BLOCK = /([^{}]+)\{([^{}]*)\}/g
const CUSTOM_PROPERTY = /(--[\w-]+)\s*:/g
const THEME_MENTION = /data-theme|dataset\.theme/

type Pair = readonly [ThemeName, string, string, number]

function themePairs(theme: ThemeName, names: readonly string[]): Pair[] {
  const texts = names.filter(
    (name) =>
      name.startsWith("--text-") && !name.startsWith("--text-on-") && !EXEMPT_TEXT.has(name),
  )
  const plain = texts.flatMap((text) =>
    TEXT_SURFACES.map((surface): Pair => [theme, text, surface, MIN_CONTRAST]),
  )
  const on = Object.entries(ON_SURFACES).flatMap(([text, backs]) =>
    backs.map((back): Pair => [theme, text, back, MIN_CONTRAST]),
  )
  const extra = EXTRA_TEXT.map(([text, back]): Pair => [theme, text, back, MIN_CONTRAST])
  const fixed = NON_TEXT.map(([front, back]): Pair => [theme, front, back, MIN_NON_TEXT_CONTRAST])
  return [...plain, ...on, ...extra, ...fixed]
}

export function contrastPairs(tables: ThemeTables): Pair[] {
  return (["light", "dark"] as const).flatMap((theme) =>
    themePairs(theme, [...tables[theme].keys()]),
  )
}

export const contrast: Check = {
  id: "contrast",
  run: (files) => {
    const tables = themeTables(files)
    if (!tables.light.has("--surface-raised"))
      return [{ file: SEMANTIC_FILE, message: "semantic tokens are missing" }]
    return contrastPairs(tables).flatMap(([theme, front, back, minimum]): Violation[] => {
      const table = tables[theme]
      const foreground = resolveName(table, front)
      const background = resolveName(table, back)
      if (foreground === null || background === null)
        return [{ file: SEMANTIC_FILE, message: `${theme}: cannot resolve ${front} on ${back}` }]
      const ratio = ratioOf(foreground, background)
      if (ratio >= minimum) return []
      return [
        {
          file: SEMANTIC_FILE,
          message: `${theme}: ${front} on ${back} is ${ratio.toFixed(2)}:1, needs ${minimum}:1`,
        },
      ]
    })
  },
}

function scopedNames(text: string): { light: Set<string>; dark: Set<string>; hasLight: boolean } {
  const light = new Set<string>()
  const dark = new Set<string>()
  let hasLight = false
  for (const block of text.matchAll(BLOCK)) {
    const selector = block[1] ?? ""
    const scope = scopeOf(selector)
    if (selector.includes('[data-theme="light"]')) hasLight = true
    const target = scope === "dark" ? dark : scope === "base" ? light : null
    for (const match of (block[2] ?? "").matchAll(CUSTOM_PROPERTY)) target?.add(match[1] ?? "")
  }
  return { light, dark, hasLight }
}

function semanticProblems(semantic: SourceFile): string[] {
  const { light, dark, hasLight } = scopedNames(semantic.text)
  return [
    ...(hasLight ? [] : ['no :root[data-theme="light"] block']),
    ...(dark.size === 0 ? ['no :root[data-theme="dark"] block'] : []),
    ...[...light].filter((name) => !dark.has(name)).map((name) => `${name} has no dark value`),
    ...[...dark].filter((name) => !light.has(name)).map((name) => `${name} has no light value`),
  ]
}

export const themeParity: Check = {
  id: "theme-parity",
  run: (files) => {
    const semantic = files.find((file) => file.path === SEMANTIC_FILE)
    if (semantic === undefined) return [{ file: SEMANTIC_FILE, message: "semantic.css is missing" }]
    const own = semanticProblems(semantic).map((message) => ({ file: semantic.path, message }))
    const otherTokens = files
      .filter((file) => file.path.startsWith(TOKENS_DIR) && file.path !== SEMANTIC_FILE)
      .filter((file) => THEME_MENTION.test(file.text))
      .map((file) => ({ file: file.path, message: "theme scope outside semantic.css" }))
    const components = [...componentStyles(files), ...sourceScripts(files)]
      .filter((file) => !file.path.startsWith(THEME_OWNER) && THEME_MENTION.test(file.text))
      .map((file) => ({ file: file.path, message: "component depends on the theme" }))
    return [...own, ...otherTokens, ...components]
  },
}
