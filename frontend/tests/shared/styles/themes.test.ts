import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { contrast, themeParity } from "../../../scripts/checks/rules/css/themeTokens.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const TOKENS = "src/shared/styles/tokens"
const files: SourceFile[] = readdirSync(resolve(process.cwd(), TOKENS)).map((name) => ({
  path: `${TOKENS}/${name}`,
  text: readFileSync(join(process.cwd(), TOKENS, name), "utf8"),
}))

describe("themes", () => {
  it("defines every semantic token in both the light and the dark theme", () => {
    expect(themeParity.run(files)).toEqual([])
  })

  it("keeps text at 4.5:1 and the focus ring at 3:1 in both themes", () => {
    expect(contrast.run(files)).toEqual([])
  })
})
