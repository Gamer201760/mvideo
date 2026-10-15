import { type AstNode, parseScript, walkAst } from "../../parse.ts"
import { API_DIR, type Check, type SourceFile, sourceScripts, type Violation } from "../../types.ts"
import { runtimeImports } from "./importCycles.ts"

const HTTP_PACKAGES = new Set(["axios", "ky", "ofetch", "superagent", "got", "node-fetch"])
const API_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
const EFFECT_HOOKS = new Set(["useEffect", "useLayoutEffect"])
const GLOBALS = new Set(["window", "globalThis", "self"])

function calleeOf(node: AstNode): AstNode | undefined {
  return node.type === "CallExpression" ? (node.callee as AstNode | undefined) : undefined
}

function propertyName(node: AstNode | undefined): string {
  const property = node?.property as AstNode | undefined
  return String(property?.name ?? property?.value ?? "")
}

function objectName(node: AstNode | undefined): string {
  const object = node?.object as AstNode | undefined
  return object?.type === "Identifier" ? String(object.name) : ""
}

export function isRawFetch(node: AstNode): boolean {
  const callee = calleeOf(node)
  if (callee?.type === "Identifier") return callee.name === "fetch"
  return (
    callee?.type === "MemberExpression" &&
    propertyName(callee) === "fetch" &&
    GLOBALS.has(objectName(callee))
  )
}

function isApiCall(node: AstNode): boolean {
  const callee = calleeOf(node)
  return callee?.type === "MemberExpression" && API_METHODS.has(propertyName(callee))
}

function effectRequests(node: AstNode): number {
  const callee = calleeOf(node)
  if (callee?.type !== "Identifier" || !EFFECT_HOOKS.has(String(callee.name))) return 0
  const [effect] = (node.arguments as readonly AstNode[] | undefined) ?? []
  let found = 0
  if (effect !== undefined)
    walkAst(effect, (inner) => {
      if (isApiCall(inner) || isRawFetch(inner)) found += 1
    })
  return found
}

export function requestProblems(file: SourceFile): string[] {
  const problems = runtimeImports(file)
    .filter((specifier) => HTTP_PACKAGES.has(specifier))
    .map((specifier) => `${specifier} instead of the api client`)
  walkAst(parseScript(file.path, file.text).program, (node) => {
    if (isRawFetch(node)) problems.push("fetch outside shared/api")
    const inEffect = effectRequests(node)
    if (inEffect > 0) problems.push("request inside an effect instead of TanStack Query")
  })
  return problems
}

export const rawRequests: Check = {
  id: "raw-requests",
  run: (files) =>
    sourceScripts(files)
      .filter((file) => !file.path.startsWith(API_DIR))
      .flatMap((file) =>
        requestProblems(file).map((message): Violation => ({ file: file.path, message })),
      ),
}
