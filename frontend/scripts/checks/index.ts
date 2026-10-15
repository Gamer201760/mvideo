import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import {
  compareWithBaseline,
  countByFile,
  formatBaseline,
  parseBaseline,
  prunedBaseline,
} from "./baseline.ts"
import { collectFiles, frontendRoot, MissingSourcesError } from "./files.ts"
import { CHECKS } from "./registry.ts"
import type { Check, SourceFile, Violation } from "./types.ts"

const root = frontendRoot(import.meta.dirname)
const baselineDir = join(root, "scripts", "baselines")
const prune = process.argv.includes("--prune")
const recordMissing = process.argv.includes("--record-missing")
const onlyIndex = process.argv.indexOf("--only")
const only = onlyIndex === -1 ? null : new Set((process.argv[onlyIndex + 1] ?? "").split(","))

const write = (line: string) => process.stdout.write(`${line}\n`)

function baselinePath(check: Check): string {
  return join(baselineDir, `${check.id}.txt`)
}

function readBaseline(check: Check, current: ReadonlyMap<string, number>) {
  const path = baselinePath(check)
  if (!existsSync(path) && recordMissing && current.size > 0) {
    mkdirSync(baselineDir, { recursive: true })
    writeFileSync(path, formatBaseline(current))
  }
  return existsSync(path) ? parseBaseline(readFileSync(path, "utf8")) : new Map<string, number>()
}

function runCheck(check: Check, files: readonly SourceFile[]): boolean {
  const violations: readonly Violation[] = check.run(files)
  const current = countByFile(violations)
  const baseline = readBaseline(check, current)
  const { regressions, improvements } = compareWithBaseline(current, baseline)
  for (const regression of regressions) {
    write(
      `  ${check.id}: ${regression.file} has ${regression.current}, allowed ${regression.allowed}`,
    )
    for (const violation of violations.filter((item) => item.file === regression.file)) {
      write(`    ${violation.message}`)
    }
  }
  if (improvements.length > 0 && prune)
    writeFileSync(baselinePath(check), formatBaseline(prunedBaseline(current, baseline)))
  if (improvements.length > 0 && !prune) {
    write(
      `  ${check.id}: ${improvements.length} baseline entries improved, run npm run rules -- --prune`,
    )
  }
  const known = [...baseline.values()].reduce((sum, count) => sum + count, 0)
  write(`${regressions.length === 0 ? "ok  " : "FAIL"} ${check.id} (${known} in baseline)`)
  return regressions.length === 0
}

function runAll(files: readonly SourceFile[]): number {
  const selected = CHECKS.filter((check) => only === null || only.has(check.id))
  const failed = selected.map((check) => runCheck(check, files)).filter((passed) => !passed).length
  write(failed === 0 ? `rules: ${selected.length} checks passed` : `rules: ${failed} checks failed`)
  return failed === 0 ? 0 : 1
}

try {
  process.exitCode = runAll(collectFiles(root))
} catch (error) {
  if (!(error instanceof MissingSourcesError)) throw error
  write(error.message)
  process.exitCode = 2
}
