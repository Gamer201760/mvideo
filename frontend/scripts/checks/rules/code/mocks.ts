import { type AstNode, parseScript, walkAst } from "../../parse.ts"
import { type Check, type SourceFile, sourceScripts, type Violation } from "../../types.ts"
import { runtimeImports } from "./importCycles.ts"

const MOCK_PACKAGES = [
  "msw",
  "@mswjs/",
  "miragejs",
  "json-server",
  "fetch-mock",
  "axios-mock-adapter",
  "pretender",
  "nock",
  "@faker-js/faker",
  "faker",
  "casual",
  "chance",
]
const DEPENDENCY_GROUPS = [
  "dependencies",
  "devDependencies",
  "peerDependencies",
  "optionalDependencies",
]
const MOCK_WORDS = new Set([
  "mock",
  "mocks",
  "mocked",
  "fake",
  "fakes",
  "faked",
  "stub",
  "stubs",
  "stubbed",
  "dummy",
  "dummies",
  "fixture",
  "fixtures",
])
const DATA_KEYS = new Set(["initialData", "placeholderData"])
const FUNCTION_KEYS = new Set(["queryFn", "mutationFn"])
const LITERALS = new Set(["ArrayExpression", "ObjectExpression", "Literal", "TemplateLiteral"])

function isMockPackage(name: string): boolean {
  return MOCK_PACKAGES.some((entry) =>
    entry.endsWith("/") ? name.startsWith(entry) : name === entry || name.startsWith(`${entry}/`),
  )
}

export function mockWords(name: string): string[] {
  return name
    .replace(/([a-z\d])([A-Z])/g, "$1 $2")
    .split(/[^A-Za-z]+/)
    .map((word) => word.toLowerCase())
    .filter((word) => MOCK_WORDS.has(word))
}

function keyName(node: AstNode): string {
  const key = node.key as AstNode | undefined
  return String(key?.name ?? key?.value ?? "")
}

function isFilledLiteral(node: AstNode | undefined): boolean {
  if (node === undefined) return false
  if (node.type === "ArrayExpression") return ((node.elements as unknown[]) ?? []).length > 0
  if (node.type === "ObjectExpression") return ((node.properties as unknown[]) ?? []).length > 0
  return false
}

function isResolvedLiteral(node: AstNode | undefined): boolean {
  if (node?.type !== "CallExpression") return false
  const callee = node.callee as AstNode | undefined
  const object = callee?.object as AstNode | undefined
  const property = callee?.property as AstNode | undefined
  const [value] = (node.arguments as readonly AstNode[] | undefined) ?? []
  return (
    object?.name === "Promise" && property?.name === "resolve" && LITERALS.has(value?.type ?? "")
  )
}

function returnsCanned(fn: AstNode | undefined): boolean {
  if (fn === undefined || !String(fn.type).includes("Function")) return false
  const body = fn.body as AstNode | undefined
  if (body === undefined) return false
  if (body.type !== "BlockStatement") return LITERALS.has(body.type) || isResolvedLiteral(body)
  let canned = false
  walkAst(body, (node) => {
    if (node.type !== "ReturnStatement") return
    const argument = node.argument as AstNode | undefined
    if (LITERALS.has(argument?.type ?? "") || isResolvedLiteral(argument)) canned = true
  })
  return canned
}

function scriptProblems(file: SourceFile): string[] {
  const problems: string[] = []
  const segment = /(^|[/._-])(__mocks__|mocks?|fakes?|stubs?|dummy|dummies|fixtures?)([/._-]|$)/i
  if (segment.test(file.path.slice("src/".length))) problems.push("mock data file in src")
  for (const specifier of runtimeImports(file))
    if (isMockPackage(specifier)) problems.push(`${specifier} serves fake responses`)
  const names = new Set<string>()
  walkAst(parseScript(file.path, file.text).program, (node) => {
    if (node.type === "Identifier" && mockWords(String(node.name)).length > 0)
      names.add(String(node.name))
    if (node.type !== "Property") return
    const value = node.value as AstNode | undefined
    if (DATA_KEYS.has(keyName(node)) && isFilledLiteral(value))
      problems.push(`${keyName(node)} with literal data`)
    if (FUNCTION_KEYS.has(keyName(node)) && returnsCanned(value))
      problems.push(`${keyName(node)} returns a canned response instead of calling the api`)
  })
  for (const name of names) problems.push(`mock identifier ${name}`)
  return problems
}

function manifestProblems(files: readonly SourceFile[]): Violation[] {
  const manifest = files.find((file) => file.path === "package.json")
  if (manifest === undefined) return []
  const parsed = JSON.parse(manifest.text) as Record<string, Record<string, string> | undefined>
  return DEPENDENCY_GROUPS.flatMap((group) => Object.keys(parsed[group] ?? {}))
    .filter(isMockPackage)
    .map((name) => ({ file: manifest.path, message: `${name} serves fake data` }))
}

export const noMocks: Check = {
  id: "no-mocks",
  run: (files) => [
    ...manifestProblems(files),
    ...sourceScripts(files).flatMap((file) =>
      scriptProblems(file).map((message): Violation => ({ file: file.path, message })),
    ),
  ],
}
