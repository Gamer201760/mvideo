import type postcss from "postcss"
import { parseStyles } from "../../parse.ts"
import { type Check, isSource, STYLES_DIR, type Violation } from "../../types.ts"

const HOVER_MEDIA = /\(hover:\s*hover\)\s+and\s+\(pointer:\s*fine\)/
const FOCUS = ":focus-visible"

function insideHoverMedia(rule: postcss.Rule): boolean {
  let parent: postcss.Node | undefined = rule.parent as postcss.Node | undefined
  while (parent !== undefined) {
    if (parent.type === "atrule" && HOVER_MEDIA.test((parent as postcss.AtRule).params)) return true
    parent = parent.parent as postcss.Node | undefined
  }
  return false
}

function isComponentStyle(path: string): boolean {
  return isSource(path) && (path.endsWith(".module.css") || path.startsWith(STYLES_DIR))
}

function animates(rule: postcss.Rule | undefined): boolean {
  let found = false
  rule?.walkDecls(/^(transition|animation)/, (declaration) => {
    if (declaration.value !== "none") found = true
  })
  return found
}

function focusProblems(rule: postcss.Rule, bases: ReadonlyMap<string, postcss.Rule>): string[] {
  if (!rule.selector.includes(FOCUS) || rule.selector.includes(`(${FOCUS}`)) return []
  if (animates(rule)) return [`${rule.selector} animates focus`]
  let resets = false
  let changes = false
  rule.walkDecls((declaration) => {
    if (declaration.prop === "transition" && declaration.value === "none") resets = true
    else if (!declaration.prop.startsWith("outline")) changes = true
  })
  const base = bases.get(rule.selector.replaceAll(FOCUS, ""))
  return changes && !resets && animates(base)
    ? [`${rule.selector} change is animated by its base transition`]
    : []
}

export function hoverProblems(text: string): string[] {
  const problems: string[] = []
  const root = parseStyles(text)
  const bases = new Map<string, postcss.Rule>()
  root.walkRules((rule) => {
    bases.set(rule.selector, rule)
  })
  root.walkRules((rule) => {
    if (rule.selector.includes(":hover") && !insideHoverMedia(rule))
      problems.push(`${rule.selector} hovers outside (hover: hover) and (pointer: fine)`)
    problems.push(...focusProblems(rule, bases))
  })
  return problems
}

export const hoverGate: Check = {
  id: "hover-gate",
  run: (files) =>
    files
      .filter((file) => isComponentStyle(file.path))
      .flatMap((file) =>
        hoverProblems(file.text).map((message): Violation => ({ file: file.path, message })),
      ),
}
