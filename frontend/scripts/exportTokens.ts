import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { readTokenSources, TOKEN_FILES, type TokenSource } from "./tokenSources.ts"

export const FONT_PACKAGES = [
  "@fontsource-variable/inter",
  "@fontsource-variable/jetbrains-mono",
] as const

export const THEMED_CONTRACT = [
  "--surface-base",
  "--surface-raised",
  "--surface-sunken",
  "--text-primary",
  "--text-secondary",
  "--text-muted",
  "--border-subtle",
  "--border-strong",
  "--action-primary",
  "--action-primary-text",
  "--focus-ring",
  "--status-success",
  "--status-warning",
  "--status-danger",
] as const

export const GLOBAL_CONTRACT = [
  "--font-sans",
  "--font-mono",
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--radius-pill",
  "--ease-out",
  "--ease-in-out",
  "--ease-drawer",
  "--dur-fast",
  "--dur-base",
  "--dur-panel",
  "--dur-slow",
  "--dur-draw",
] as const

const COMMENT = /\/\*[\s\S]*?\*\//g
const ROOT_THEME = /:root\[data-theme=/g
const PACKAGE_FONT_URL = /url\(\.\/files\/([\w.-]+)\)/g
const KEPT_FACE = /\/\*\s*[\w-]+?-(latin|latin-ext|cyrillic|cyrillic-ext)-wght-normal\s*\*\/\s*$/
const BLOCK = /([^{}]+)\{([^{}]*)\}/g

export function buildTokenCss(sources: readonly TokenSource[]): string {
  const ordered = TOKEN_FILES.map((name) => sources.find((source) => source.name === name))
  const missing = TOKEN_FILES.filter((_, index) => ordered[index] === undefined)
  if (missing.length > 0) throw new Error(`missing token files: ${missing.join(", ")}`)
  const text = ordered.map((source) => (source?.text ?? "").replace(COMMENT, "").trim())
  return `${text.join("\n\n").replace(ROOT_THEME, "[data-theme=")}\n`
}

function declaredIn(css: string, matches: (selector: string) => boolean): Set<string> {
  const names = new Set<string>()
  for (const block of css.matchAll(BLOCK)) {
    if (!matches((block[1] ?? "").trim())) continue
    for (const match of (block[2] ?? "").matchAll(/(--[\w-]+)\s*:/g)) names.add(match[1] ?? "")
  }
  return names
}

export function contractGaps(css: string): string[] {
  const light = declaredIn(css, (selector) => selector.includes('[data-theme="light"]'))
  const dark = declaredIn(css, (selector) => selector === '[data-theme="dark"]')
  const root = declaredIn(css, (selector) => selector === ":root")
  return [
    ...THEMED_CONTRACT.filter((name) => !light.has(name)).map((name) => `${name} (light)`),
    ...THEMED_CONTRACT.filter((name) => !dark.has(name)).map((name) => `${name} (dark)`),
    ...GLOBAL_CONTRACT.filter((name) => !root.has(name)),
  ]
}

export interface FontFaces {
  readonly css: string
  readonly files: readonly string[]
}

export function pickFontFaces(css: string): FontFaces {
  const parts = css.split("@font-face")
  const kept = parts.slice(1).filter((_, index) => KEPT_FACE.test(parts[index] ?? ""))
  const files = kept.flatMap((block) =>
    [...block.matchAll(PACKAGE_FONT_URL)].map((match) => match[1] ?? ""),
  )
  const text = kept
    .map((block) => {
      const body = block.slice(0, block.indexOf("}") + 1).trim()
      return `@font-face ${body.replace(PACKAGE_FONT_URL, 'url("fonts/$1")')}`
    })
    .join("\n")
  return { css: text, files }
}

function copyFonts(frontendRoot: string, target: string): string {
  const fontsDir = join(dirname(target), "fonts")
  mkdirSync(fontsDir, { recursive: true })
  return FONT_PACKAGES.map((name) => {
    const packageDir = join(frontendRoot, "node_modules", ...name.split("/"))
    const faces = pickFontFaces(readFileSync(join(packageDir, "index.css"), "utf8"))
    for (const file of faces.files)
      copyFileSync(join(packageDir, "files", file), join(fontsDir, file))
    return faces.css
  }).join("\n")
}

export function tokenCss(frontendRoot: string): string {
  const css = buildTokenCss(readTokenSources(frontendRoot))
  const gaps = contractGaps(css)
  if (gaps.length > 0) throw new Error(`tokens:export: deck contract is missing ${gaps.join(", ")}`)
  return css
}

export function exportTokens(frontendRoot: string, target: string, withFonts: boolean): string {
  const tokens = tokenCss(frontendRoot)
  const css = withFonts ? `${copyFonts(frontendRoot, target)}\n\n${tokens}` : tokens
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, css)
  return css
}

const frontendRoot = resolve(fileURLToPath(new URL("..", import.meta.url)))
const DEFAULT_TARGET = join(frontendRoot, "..", "presentation", "src", "core", "css", "tokens.css")

function option(name: string): string | undefined {
  const index = process.argv.indexOf(`--${name}`)
  return index === -1 ? undefined : process.argv[index + 1]
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.includes("--print")) {
    process.stdout.write(tokenCss(frontendRoot))
  } else {
    const target = resolve(option("out") ?? DEFAULT_TARGET)
    exportTokens(frontendRoot, target, process.argv.includes("--fonts"))
    process.stdout.write(`tokens exported to ${target}\n`)
  }
}
