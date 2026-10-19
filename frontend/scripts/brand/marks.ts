import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import type { ThemeName } from "../checks/themes.ts"
import { readTokenSources, themeColor } from "../tokenSources.ts"

export interface ThemePalette {
  readonly base: string
  readonly accent: string
  readonly surface: string
  readonly raised: string
  readonly muted: string
  readonly line: string
  readonly shell: string
}

export type BrandPalette = Readonly<Record<ThemeName, ThemePalette>>

export interface Mark {
  readonly viewBox: string
  readonly body: string
}

const SVG = /<svg\b[^>]*\bviewBox="([^"]+)"[^>]*>([\s\S]*?)<\/svg>/
const SHELL_MARK = /<template id="brand-mark">\s*([\s\S]*?)\s*<\/template>/

const PALETTE_TOKENS: Readonly<Record<keyof ThemePalette, string>> = {
  base: "--text-primary",
  accent: "--mark-thread",
  surface: "--surface-base",
  raised: "--surface-raised",
  muted: "--text-secondary",
  line: "--border-subtle",
  shell: "--surface-shell",
}

export function readMark(repoRoot: string): Mark {
  const localSymbol = join(repoRoot, "frontend", "brand", "mark.svg")
  const symbol = existsSync(localSymbol)
    ? localSymbol
    : join(repoRoot, "docs", "brand", "symbol.svg")
  const shell = join(repoRoot, "presentation", "src", "shell.html")
  const svg = existsSync(symbol)
    ? readFileSync(symbol, "utf8")
    : (SHELL_MARK.exec(readFileSync(shell, "utf8"))?.[1] ?? "")
  const match = SVG.exec(svg)
  if (match === null)
    throw new Error(
      "brand mark not found: docs/brand/symbol.svg or brand-mark in presentation/src/shell.html",
    )
  return { viewBox: match[1] ?? "0 0 32 32", body: (match[2] ?? "").trim() }
}

export function readPalette(frontendRoot: string): BrandPalette {
  const sources = readTokenSources(frontendRoot)
  const pick = (theme: ThemeName): ThemePalette => {
    const entries = Object.entries(PALETTE_TOKENS).map(([key, token]) => {
      const color = themeColor(sources, theme, token)
      if (color === null) throw new Error(`token ${token} has no ${theme} value`)
      return [key, color]
    })
    return Object.fromEntries(entries) as unknown as ThemePalette
  }
  return { light: pick("light"), dark: pick("dark") }
}

function markStyle(colors: ThemePalette): string {
  return `.mark-base{fill:${colors.base}}.mark-accent{fill:${colors.accent}}`
}

export function faviconSvg(mark: Mark, palette: BrandPalette): string {
  const style = `${markStyle(palette.light)}@media (prefers-color-scheme:dark){${markStyle(palette.dark)}}`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${mark.viewBox}"><style>${style}</style>${mark.body}</svg>\n`
}

export function paintedMark(mark: Mark, colors: ThemePalette): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${mark.viewBox}" width="100%" height="100%"><style>${markStyle(colors)}</style>${mark.body}</svg>`
}
