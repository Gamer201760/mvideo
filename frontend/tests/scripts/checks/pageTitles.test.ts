import { describe, expect, it } from "vitest"
import { pageTitles } from "../../../scripts/checks/rules/code/pageTitles.ts"
import { TITLE_FILE, textSeparators } from "../../../scripts/checks/rules/text/separators.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text: string): SourceFile => ({ path, text })

describe("page-titles", () => {
  it("passes pages that set a tab title, the home page with null", () => {
    const files = [
      file(
        "src/pages/orders/orders-page.tsx",
        'export const P = () => { useDocumentTitle(t("orders:title")) }\n',
      ),
      file("src/pages/home/home-page.tsx", "export const H = () => { useDocumentTitle(null) }\n"),
      file("src/features/list/list.tsx", "export const L = () => null\n"),
    ]
    expect(pageTitles.run(files)).toEqual([])
  })

  it("reports a page without a tab title", () => {
    const [violation] = pageTitles.run([
      file("src/pages/orders/orders-page.tsx", "export const P = () => null\n"),
    ])
    expect(violation?.file).toBe("src/pages/orders/orders-page.tsx")
  })
})

describe("text-separators and the title separator", () => {
  it("allows the pipe only in the document title module", () => {
    const text = 'export const S = " | "\n'
    expect(textSeparators.run([file(TITLE_FILE, text)])).toEqual([])
    expect(textSeparators.run([file("src/features/a/a.ts", text)])).toHaveLength(1)
  })
})
