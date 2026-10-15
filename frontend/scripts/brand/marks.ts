import { readFileSync } from "node:fs"
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
}

export type BrandPalette = Readonly<Record<ThemeName, ThemePalette>>

export interface Mark {
  readonly viewBox: string
  readonly body: string
}

const SVG = /<svg\b[^>]*\bviewBox="([^"]+)"[^>]*>([\s\S]*?)<\/svg>/

const PALETTE_TOKENS: Readonly<Record<keyof ThemePalette, string>> = {
  base: "--text-primary",
  accent: "--action-primary",
  surface: "--surface-base",
  raised: "--surface-raised",
  muted: "--text-secondary",
  line: "--border-subtle",
}

export function readMark(frontendRoot: string): Mark {
  const svg = readFileSync(join(frontendRoot, "brand", "mark.svg"), "utf8")
  const match = SVG.exec(svg)
  if (match === null) throw new Error("brand mark not found: brand/mark.svg")
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
