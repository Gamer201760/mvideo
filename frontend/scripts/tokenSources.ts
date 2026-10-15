import { readFileSync } from "node:fs"
import { join } from "node:path"
import { toHex } from "./checks/color.ts"
import { resolveName, type ThemeName, themeTables } from "./checks/themes.ts"
import { type SourceFile, TOKENS_DIR } from "./checks/types.ts"

export const TOKEN_FILES = [
  "palette.css",
  "semantic.css",
  "radius.css",
  "space.css",
  "typography.css",
  "elevation.css",
  "motion.css",
  "keyframes.css",
] as const

export type TokenFileName = (typeof TOKEN_FILES)[number]

export interface TokenSource {
  readonly name: TokenFileName
  readonly text: string
}

export function readTokenSources(frontendRoot: string): TokenSource[] {
  const tokensDir = join(frontendRoot, ...TOKENS_DIR.split("/"))
  return TOKEN_FILES.map((name) => ({ name, text: readFileSync(join(tokensDir, name), "utf8") }))
}

export function asSourceFiles(sources: readonly TokenSource[]): SourceFile[] {
  return sources.map((source) => ({ path: `${TOKENS_DIR}${source.name}`, text: source.text }))
}

export function themeColor(
  sources: readonly TokenSource[],
  theme: ThemeName,
  name: string,
): string | null {
  const color = resolveName(themeTables(asSourceFiles(sources))[theme], name)
  return color === null ? null : toHex(color)
}
