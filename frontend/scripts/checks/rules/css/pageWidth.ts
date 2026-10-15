import { expandVars, localProperties } from "../../cssVars.ts"
import { resolvePixels } from "../../lengths.ts"
import { parseStyles } from "../../parse.ts"
import { type TokenTable, tokenFile, tokenTable } from "../../tokens.ts"
import { type Check, componentStyles, TOKENS_DIR, type Violation } from "../../types.ts"

export const PROSE_LIMIT_CH = 70
export const FIELD_LIMIT_PX = 480
export const MEASURE_TOKENS: Readonly<Record<string, "ch" | "px">> = {
  "--prose-measure": "ch",
  "--field-max-width": "px",
}
const WIDTH_CAP = /^max-(width|inline-size)$/
const FREE_VALUE = /^(none|100%|min-content|max-content|fit-content|inherit|initial|unset)$/
const NO_TOKENS: TokenTable = new Map()

function allowedCap(value: string, local: ReadonlyMap<string, readonly string[]>): boolean {
  return expandVars(value, local, NO_TOKENS).every((variant) => {
    const trimmed = variant.trim()
    if (FREE_VALUE.test(trimmed)) return true
    const token = /^var\((--[\w-]+)\)$/.exec(trimmed)?.[1]
    return token !== undefined && token in MEASURE_TOKENS
  })
}

function tokenProblems(tokens: TokenTable, files: Parameters<Check["run"]>[0]): Violation[] {
  const space = tokenFile(files, "space.css")
  const file = space?.path ?? `${TOKENS_DIR}space.css`
  const prose = /^(\d*\.?\d+)ch$/.exec(tokens.get("--prose-measure") ?? "")
  const field = resolvePixels("var(--field-max-width)", new Map(), tokens)
  const problems: Violation[] = []
  if (prose === null || Number(prose[1]) > PROSE_LIMIT_CH)
    problems.push({ file, message: `--prose-measure must be at most ${PROSE_LIMIT_CH}ch` })
  if (field === null || field > FIELD_LIMIT_PX)
    problems.push({ file, message: `--field-max-width must be at most ${FIELD_LIMIT_PX}px` })
  return problems
}

export const pageWidth: Check = {
  id: "page-width",
  run: (files) => {
    const tokens = tokenTable(files)
    const capped = componentStyles(files).flatMap((file) => {
      const local = localProperties(file.text)
      const found: Violation[] = []
      parseStyles(file.text).walkDecls(WIDTH_CAP, (declaration) => {
        if (allowedCap(declaration.value, local)) return
        found.push({
          file: file.path,
          message: `width cap outside prose and field measures: ${declaration.prop}: ${declaration.value}`,
        })
      })
      return found
    })
    return [...tokenProblems(tokens, files), ...capped]
  },
}
