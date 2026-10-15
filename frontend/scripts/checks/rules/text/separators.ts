import { type AstNode, literalStrings, parseScript, walkAst } from "../../parse.ts"
import {
  type Check,
  isDictionary,
  isGenerated,
  type SourceFile,
  sourceScripts,
  type Violation,
} from "../../types.ts"

export const TITLE_FILE = "src/shared/i18n/document-title.ts"
const MIDDLE_DOT = /[·•∙]/
const EM_DASH = /—/
const PIPE_SEPARATOR = /\s\|\s/
const EN_DASH = /–/g
const NUMERIC_SIDE = /(\d|\}\})\s*$/
const NUMERIC_START = /^\s*(\d|\{\{)/
const GLYPH =
  /[\u2190-\u21FF\u27F0-\u27FF\u2900-\u297F\u2794\u279C\u279D\u27A1\u2705\u2713-\u2718\u274C\u274E\u25B6\u25B8\u25BA\u25C0\u25C2\u25C4]/u
const EMOJI = /(?:[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]|\u{FE0F})/u

type Tree = { readonly [key: string]: unknown }

export function dictionaryValues(text: string): string[] {
  const walk = (value: unknown): string[] => {
    if (typeof value === "string") return [value]
    if (typeof value !== "object" || value === null) return []
    return Object.values(value as Tree).flatMap(walk)
  }
  try {
    return walk(JSON.parse(text))
  } catch {
    return []
  }
}

function strayEnDash(text: string): boolean {
  for (const match of text.matchAll(EN_DASH)) {
    const index = match.index ?? 0
    const before = text.slice(0, index)
    const after = text.slice(index + 1)
    if (!NUMERIC_SIDE.test(before) || !NUMERIC_START.test(after)) return true
  }
  return false
}

export function separatorProblems(text: string): string[] {
  const problems: string[] = []
  if (MIDDLE_DOT.test(text)) problems.push("dot separator")
  if (EM_DASH.test(text)) problems.push("em dash")
  if (PIPE_SEPARATOR.test(text)) problems.push("pipe separator")
  if (strayEnDash(text)) problems.push("en dash outside a numeric range")
  return problems
}

function scriptStrings(file: SourceFile): string[] {
  const found: string[] = []
  walkAst(parseScript(file.path, file.text).program, (node: AstNode) => {
    if (node.type === "Literal" || node.type === "TemplateLiteral")
      found.push(...literalStrings(node))
  })
  return found
}

function uiTexts(files: readonly SourceFile[]): [SourceFile, string[]][] {
  return [
    ...files
      .filter((file) => isDictionary(file.path))
      .map((file): [SourceFile, string[]] => [file, dictionaryValues(file.text)]),
    ...sourceScripts(files)
      .filter((file) => !isGenerated(file.path))
      .map((file): [SourceFile, string[]] => [file, scriptStrings(file)]),
  ]
}

export const textSeparators: Check = {
  id: "text-separators",
  run: (files) =>
    uiTexts(files).flatMap(([file, texts]) =>
      texts.flatMap((text) =>
        separatorProblems(text)
          .filter((problem) => !(file.path === TITLE_FILE && problem === "pipe separator"))
          .map(
            (problem): Violation => ({
              file: file.path,
              message: `${problem}: ${text.slice(0, 60)}`,
            }),
          ),
      ),
    ),
}

export const symbolGlyphs: Check = {
  id: "symbol-glyphs",
  run: (files) =>
    uiTexts(files).flatMap(([file, texts]) =>
      texts
        .filter((text) => GLYPH.test(text))
        .map(
          (text): Violation => ({
            file: file.path,
            message: `arrow, check or pointer glyph, use an Icon: ${text.slice(0, 60)}`,
          }),
        ),
    ),
}

export const noEmoji: Check = {
  id: "no-emoji",
  run: (files) =>
    uiTexts(files).flatMap(([file, texts]) =>
      texts
        .filter((text) => EMOJI.test(text))
        .map((text): Violation => ({ file: file.path, message: `emoji: ${text.slice(0, 60)}` })),
    ),
}
