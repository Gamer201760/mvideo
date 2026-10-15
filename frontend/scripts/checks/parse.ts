import postcss from "postcss"
import { parseSync } from "rolldown/utils"

export interface ScriptComment {
  readonly type: string
  readonly value: string
}

export interface AstNode {
  readonly type: string
  readonly [key: string]: unknown
}

export interface ParsedScript {
  readonly program: AstNode
  readonly comments: readonly ScriptComment[]
}

const scriptCache = new Map<string, ParsedScript>()
const styleCache = new Map<string, postcss.Root>()

export function parseScript(path: string, text: string): ParsedScript {
  const key = `${path}\u0000${text}`
  const cached = scriptCache.get(key)
  if (cached !== undefined) return cached
  const result = parseSync(path, text)
  const parsed = {
    program: result.program as unknown as AstNode,
    comments: result.comments as readonly ScriptComment[],
  }
  scriptCache.set(key, parsed)
  return parsed
}

function isNode(value: unknown): value is AstNode {
  return typeof value === "object" && value !== null && typeof (value as AstNode).type === "string"
}

export function walkAst(node: AstNode, visit: (node: AstNode) => void): void {
  visit(node)
  for (const [key, value] of Object.entries(node)) {
    if (key === "parent") continue
    const children = Array.isArray(value) ? value : [value]
    for (const child of children) if (isNode(child)) walkAst(child, visit)
  }
}

export function literalStrings(node: AstNode | null | undefined): string[] {
  if (node === null || node === undefined) return []
  if (node.type === "Literal") return typeof node.value === "string" ? [node.value] : []
  if (node.type === "TemplateLiteral")
    return ((node.quasis as readonly AstNode[] | undefined) ?? []).map((quasi) =>
      String((quasi.value as { cooked?: unknown } | undefined)?.cooked ?? ""),
    )
  if (node.type === "JSXExpressionContainer") return literalStrings(node.expression as AstNode)
  if (node.type === "ConditionalExpression")
    return [
      ...literalStrings(node.consequent as AstNode),
      ...literalStrings(node.alternate as AstNode),
    ]
  if (node.type === "LogicalExpression")
    return [...literalStrings(node.left as AstNode), ...literalStrings(node.right as AstNode)]
  if (node.type === "ParenthesizedExpression" || node.type === "TSAsExpression")
    return literalStrings(node.expression as AstNode)
  return []
}

export function parseStyles(text: string): postcss.Root {
  const cached = styleCache.get(text)
  if (cached !== undefined) return cached
  const root = postcss.parse(text)
  styleCache.set(text, root)
  return root
}

export interface StyleDeclaration {
  readonly prop: string
  readonly value: string
  readonly selector: string
}

export function styleDeclarations(text: string): StyleDeclaration[] {
  const declarations: StyleDeclaration[] = []
  parseStyles(text).walkDecls((declaration) => {
    const parent = declaration.parent
    const selector = parent?.type === "rule" ? (parent as postcss.Rule).selector : ""
    declarations.push({ prop: declaration.prop, value: declaration.value, selector })
  })
  return declarations
}
