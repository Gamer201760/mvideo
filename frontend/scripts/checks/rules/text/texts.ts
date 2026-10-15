import { type AstNode, literalStrings, parseScript, walkAst } from "../../parse.ts"
import {
  type Check,
  isDictionary,
  isGenerated,
  isScript,
  isSource,
  type SourceFile,
  type Violation,
} from "../../types.ts"

const CYRILLIC = new RegExp(`[${String.fromCodePoint(0x400)}-${String.fromCodePoint(0x4ff)}]`)
const CYRILLIC_ESCAPE = /\\u(04[0-9a-f]{2}|\{4[0-9a-f]{2}\})/i
const RU_LOCALE = "src/shared/i18n/locales/ru/"
const LETTER = /\p{L}/u
const TEXT_ATTRIBUTES = new Set([
  "aria-label",
  "aria-description",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
  "title",
  "placeholder",
  "alt",
  "label",
  "eyebrow",
  "description",
  "hint",
  "heading",
  "caption",
  "message",
  "legend",
  "content",
  "emptyText",
  "disabledReason",
])
const DOM_TEXT_PROPERTIES = new Set(["title", "textContent", "innerText", "ariaLabel", "alt"])
const DOM_TEXT_ATTRIBUTES = new Set(["aria-label", "title", "alt", "placeholder"])

export function allowsCyrillic(path: string): boolean {
  return (path.startsWith(RU_LOCALE) && path.endsWith(".json")) || isGenerated(path)
}

export const cyrillic: Check = {
  id: "cyrillic",
  run: (files) =>
    files.flatMap((file): Violation[] => {
      if (allowsCyrillic(file.path)) return []
      const where = isDictionary(file.path) ? "cyrillic outside the ru dictionary" : "cyrillic"
      return file.text
        .split(/\r?\n/)
        .filter((line) => CYRILLIC.test(line) || CYRILLIC_ESCAPE.test(line))
        .map((line) => ({ file: file.path, message: `${where}: ${line.trim().slice(0, 60)}` }))
    }),
}

function attributeName(node: AstNode): string {
  const name = node.name as { name?: unknown } | undefined
  return typeof name?.name === "string" ? name.name : ""
}

function withLetters(texts: readonly string[]): string[] {
  return texts.filter((text) => LETTER.test(text)).map((text) => text.trim())
}

function jsxProblems(node: AstNode, attributeValues: ReadonlySet<AstNode>): string[] {
  if (node.type === "JSXText") return withLetters([String(node.value)])
  if (node.type === "JSXExpressionContainer" && !attributeValues.has(node))
    return withLetters(literalStrings(node.expression as AstNode))
  if (node.type !== "JSXAttribute" || !TEXT_ATTRIBUTES.has(attributeName(node))) return []
  return withLetters(literalStrings(node.value as AstNode)).map(
    (text) => `${attributeName(node)}="${text}"`,
  )
}

function memberName(node: AstNode | undefined): string {
  const property = node?.property as AstNode | undefined
  return String(property?.name ?? property?.value ?? "")
}

function domProblems(node: AstNode): string[] {
  if (node.type === "AssignmentExpression") {
    const target = node.left as AstNode | undefined
    if (target?.type !== "MemberExpression" || !DOM_TEXT_PROPERTIES.has(memberName(target)))
      return []
    return withLetters(literalStrings(node.right as AstNode))
  }
  if (node.type !== "CallExpression" || memberName(node.callee as AstNode) !== "setAttribute")
    return []
  const [name, value] = (node.arguments as readonly AstNode[] | undefined) ?? []
  const attribute = name?.type === "Literal" ? String(name.value) : ""
  return DOM_TEXT_ATTRIBUTES.has(attribute) ? withLetters(literalStrings(value)) : []
}

function attributeContainers(program: AstNode): Set<AstNode> {
  const containers = new Set<AstNode>()
  walkAst(program, (node) => {
    const value = node.type === "JSXAttribute" ? (node.value as AstNode | null) : null
    if (value !== null) containers.add(value)
  })
  return containers
}

export function literalTexts(file: SourceFile): string[] {
  const program = parseScript(file.path, file.text).program
  const attributeValues = attributeContainers(program)
  const found: string[] = []
  walkAst(program, (node) => {
    found.push(...jsxProblems(node, attributeValues), ...domProblems(node))
  })
  return found
}

export const jsxText: Check = {
  id: "jsx-text",
  run: (files) =>
    files.flatMap((file): Violation[] => {
      if (!isSource(file.path) || !isScript(file.path) || isGenerated(file.path)) return []
      return literalTexts(file).map((text) => ({
        file: file.path,
        message: `literal text: ${text.slice(0, 60)}`,
      }))
    }),
}
