import { describe, expect, it } from "vitest"
import {
  noEmoji,
  separatorProblems,
  symbolGlyphs,
  textSeparators,
} from "../../../scripts/checks/rules/text/separators.ts"
import { cyrillic, jsxText } from "../../../scripts/checks/rules/text/texts.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const CYRILLIC_WORD = String.fromCodePoint(0x43f, 0x440, 0x438, 0x432, 0x435, 0x442)
const ESCAPED_WORD = ["041f", "0443", "0441", "043a"].map((code) => `\\${"u"}${code}`).join("")
const EM = String.fromCodePoint(0x2014)
const EN = String.fromCodePoint(0x2013)
const DOT = String.fromCodePoint(0xb7)
const EMOJI = String.fromCodePoint(0x1f680)
const file = (path: string, text: string): SourceFile => ({ path, text })
const dictionary = (locale: string, value: string) =>
  file(`src/shared/i18n/locales/${locale}/common.json`, JSON.stringify({ a: { b: value } }))

describe("cyrillic", () => {
  it("passes latin sources, the ru dictionary and generated files", () => {
    const files = [
      file("src/a.ts", 'export const a = "hello"\n'),
      dictionary("ru", CYRILLIC_WORD),
      file("src/shared/api/schema.gen.ts", `{"a": "${CYRILLIC_WORD}"}`),
    ]
    expect(cyrillic.run(files)).toEqual([])
  })

  it("reports each source line with cyrillic and the en dictionary", () => {
    const text = `export const a = "${CYRILLIC_WORD}"\nexport const b = "${CYRILLIC_WORD}"\n`
    expect(cyrillic.run([file("src/a.ts", text)])).toHaveLength(2)
    expect(cyrillic.run([dictionary("en", CYRILLIC_WORD)])).toHaveLength(1)
  })

  it.each(["e2e/a.spec.ts", "tests/probe/x.test.ts", "index.html", "scripts/x.ts"])(
    "scans %s too",
    (path) => {
      expect(cyrillic.run([file(path, `x = "${CYRILLIC_WORD}"\n`)])).toHaveLength(1)
    },
  )

  it("reports escaped cyrillic", () => {
    expect(cyrillic.run([file("src/a.ts", `const greeting = "${ESCAPED_WORD}"\n`)])).toHaveLength(1)
  })
})

describe("jsx-text", () => {
  it("passes translated text, punctuation and class name branches", () => {
    const text =
      'export const A = ({ on }) => <p title={t("x")} className={on ? "a" : "b"}>{t("y")}{count}{" "}</p>\n'
    expect(jsxText.run([file("src/a.tsx", text)])).toEqual([])
  })

  it("reports literal children and text attributes", () => {
    const text = 'export const A = () => <p aria-label="Close" title="Hint">Hello</p>\n'
    expect(jsxText.run([file("src/a.tsx", text)])).toHaveLength(3)
  })

  it("reports text hidden in expressions, branches and component props", () => {
    const text = [
      "export const A = ({ on }) => (",
      "  <div>",
      '    {"Start order"}',
      "    {`Stop order`}",
      '    {on ? "Running" : "Idle"}',
      '    <span aria-label={"Close dialog"} />',
      '    <img alt={"Product photo"} src="/a.png" />',
      '    <Button label="Export report" />',
      '    <Card eyebrow="Orders" />',
      "  </div>",
      ")",
    ].join("\n")
    expect(jsxText.run([file("src/features/x/index.tsx", text)])).toHaveLength(8)
  })

  it("reports literal text assigned to the document from scripts", () => {
    const text =
      'document.title = "Order panel"\nel.setAttribute("aria-label", "Close")\nel.textContent = `Ready`\n'
    expect(jsxText.run([file("src/app/title.ts", text)])).toHaveLength(3)
  })

  it("ignores tests", () => {
    const text = "export const A = () => <p>Hello</p>\n"
    expect(jsxText.run([file("tests/a.test.tsx", text)])).toEqual([])
  })
})

describe("text-separators", () => {
  it("passes sentences, colons and numeric ranges", () => {
    expect(separatorProblems("Saved. Open the list.")).toEqual([])
    expect(separatorProblems(`10${EN}20 items`)).toEqual([])
    expect(separatorProblems(`{{from}} ${EN} {{to}}`)).toEqual([])
  })

  it.each([
    [`Orders ${DOT} Today`, "dot separator"],
    [`Fast ${EM} and simple`, "em dash"],
    ["Home | Orders", "pipe separator"],
    [`Draft ${EN} saved`, "en dash outside a numeric range"],
  ])("reports %s", (text, problem) => {
    expect(separatorProblems(text)).toEqual([problem])
  })

  it("scans dictionaries and string joins in sources", () => {
    const files = [
      dictionary("en", `A ${DOT} B`),
      file("src/features/x/a.ts", `export const line = parts.join(" ${EM} ")\n`),
      file("tests/x.test.ts", `const sample = "A ${EM} B"\n`),
    ]
    expect(textSeparators.run(files).map((item) => item.file)).toEqual([
      "src/shared/i18n/locales/en/common.json",
      "src/features/x/a.ts",
    ])
  })
})

describe("symbol-glyphs", () => {
  it.each([0x2192, 0x2190, 0x21d2, 0x2713, 0x2714, 0x2717, 0x2715, 0x25b6, 0x279c])(
    "reports U+%s in dictionaries and sources",
    (code) => {
      const glyph = String.fromCodePoint(code)
      const files = [
        dictionary("en", `Next ${glyph}`),
        file(
          "src/features/x/a.tsx",
          `export const mark = "${glyph}"
`,
        ),
      ]
      expect(symbolGlyphs.run(files)).toHaveLength(2)
    },
  )

  it("passes plain words", () => {
    expect(symbolGlyphs.run([dictionary("en", "Next step")])).toEqual([])
  })
})

describe("no-emoji", () => {
  it("reports emoji in dictionaries and sources", () => {
    const files = [
      dictionary("en", `Launch ${EMOJI}`),
      file("src/features/x/a.tsx", `export const mark = "${EMOJI}"\n`),
      dictionary("ru", CYRILLIC_WORD),
    ]
    expect(noEmoji.run(files)).toHaveLength(2)
  })
})
