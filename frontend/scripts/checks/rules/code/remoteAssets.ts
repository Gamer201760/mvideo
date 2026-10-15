import { type AstNode, literalStrings, parseScript, walkAst } from "../../parse.ts"
import {
  type Check,
  isScript,
  isSource,
  isStyle,
  type SourceFile,
  type Violation,
} from "../../types.ts"

const REMOTE_REFERENCE =
  /(url\(\s*["']?|@import\s+["']|(?:href|src)=["']|srcset=["'][^"']*?)(https?:)?\/\//i
const REMOTE_STRING = /^(https?:)?\/\/(?!www\.w3\.org\/)/

function violations(file: SourceFile, messages: readonly string[]): Violation[] {
  return messages.map((message) => ({ file: file.path, message }))
}

function scriptRemoteProblems(file: SourceFile): string[] {
  const found: string[] = []
  walkAst(parseScript(file.path, file.text).program, (node: AstNode) => {
    if (node.type !== "Literal" && node.type !== "TemplateLiteral") return
    for (const text of literalStrings(node)) {
      const remote = REMOTE_STRING.test(text.trim()) || REMOTE_REFERENCE.test(text)
      if (remote) found.push(`remote asset: ${text.trim().slice(0, 80)}`)
    }
  })
  return found
}

export const remoteAssets: Check = {
  id: "remote-assets",
  run: (files) =>
    files.flatMap((file) => {
      if (isScript(file.path) && isSource(file.path))
        return violations(file, scriptRemoteProblems(file))
      if (!isStyle(file.path) && !file.path.endsWith(".html")) return []
      return violations(
        file,
        file.text
          .split(/\r?\n/)
          .filter((line) => REMOTE_REFERENCE.test(line))
          .map((line) => `remote asset: ${line.trim().slice(0, 80)}`),
      )
    }),
}
