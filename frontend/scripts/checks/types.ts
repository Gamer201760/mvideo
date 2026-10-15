export interface SourceFile {
  readonly path: string
  readonly text: string
}

export interface Violation {
  readonly file: string
  readonly message: string
  readonly weight?: number
}

export interface Check {
  readonly id: string
  readonly run: (files: readonly SourceFile[]) => readonly Violation[]
}

export function extensionOf(path: string): string {
  const dot = path.lastIndexOf(".")
  return dot === -1 ? "" : path.slice(dot)
}

export function directoryOf(path: string): string {
  const slash = path.lastIndexOf("/")
  return slash === -1 ? "" : path.slice(0, slash)
}

export const SCRIPT_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".mts",
  ".cts",
  ".mjs",
  ".cjs",
  ".js",
  ".jsx",
])

export const TOKENS_DIR = "src/shared/styles/tokens/"

export const STYLES_DIR = "src/shared/styles/"

export const LOCALES_DIR = "src/shared/i18n/locales/"

export const API_DIR = "src/shared/api/"

export const GENERATED_SCHEMA = "src/shared/api/schema.gen.ts"

export function isGenerated(path: string): boolean {
  return /\.gen\.tsx?$/.test(path)
}

export function isScript(path: string): boolean {
  return SCRIPT_EXTENSIONS.has(extensionOf(path))
}

export function isStyle(path: string): boolean {
  return path.endsWith(".css")
}

export function isTest(path: string): boolean {
  return /\.(test|spec)\.tsx?$/.test(path)
}

export function isSource(path: string): boolean {
  return path.startsWith("src/")
}

export function isDictionary(path: string): boolean {
  return path.startsWith(LOCALES_DIR) && path.endsWith(".json")
}

export function componentStyles(files: readonly SourceFile[]): SourceFile[] {
  return files.filter(
    (file) => isSource(file.path) && isStyle(file.path) && !file.path.startsWith(TOKENS_DIR),
  )
}

export function sourceScripts(files: readonly SourceFile[]): SourceFile[] {
  return files.filter((file) => isSource(file.path) && isScript(file.path))
}
