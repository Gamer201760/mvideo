import { describe, expect, it } from "vitest"
import { formatSellerLines, parseSellerLines } from "@/features/card-extraction"

describe("seller lines", () => {
  it("preserves valid pairs and reports each invalid nonempty line", () => {
    expect(parseSellerLines("Color: black\nno separator\n: empty\nSize:  XL \nWidth: ")).toEqual({
      params: [
        { name: "Color", value: "black", unit: null },
        { name: "Size", value: "XL", unit: null },
      ],
      issues: [
        { line: 2, text: "no separator", reason: "missing_separator" },
        { line: 3, text: ": empty", reason: "missing_name" },
        { line: 5, text: "Width: ", reason: "missing_value" },
      ],
    })
  })

  it("ignores whitespace lines without losing original line numbers across line endings", () => {
    expect(parseSellerLines("\r\n  \r\nMissing\rWeight:  90 g \n")).toEqual({
      params: [{ name: "Weight", value: "90 g", unit: null }],
      issues: [{ line: 3, text: "Missing", reason: "missing_separator" }],
    })
  })

  it("keeps colons inside values and treats a blank name as an error", () => {
    expect(parseSellerLines("URL: https://example.com:8080\n  : yes\n : ")).toEqual({
      params: [{ name: "URL", value: "https://example.com:8080", unit: null }],
      issues: [
        { line: 2, text: "  : yes", reason: "missing_name" },
        { line: 3, text: " : ", reason: "missing_name" },
      ],
    })
  })

  it("allows an empty optional field", () => {
    expect(parseSellerLines(" \n\t")).toEqual({ params: [], issues: [] })
  })

  it("formats params with units back to lines", () => {
    const text = formatSellerLines([
      { name: "Width", value: "90", unit: "mm" },
      { name: "Color", value: "black", unit: null },
    ])
    expect(text).toBe("Width: 90 mm\nColor: black")
    expect(parseSellerLines(text).params[0]).toEqual({ name: "Width", value: "90 mm", unit: null })
    expect(parseSellerLines(text).issues).toEqual([])
  })
})
