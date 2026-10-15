import { describe, expect, it } from "vitest"
import { formatSellerLines, parseSellerLines } from "@/features/card-extraction"

describe("seller lines", () => {
  it("parses name and value pairs and skips broken lines", () => {
    expect(parseSellerLines("Color: black\nno separator\n: empty\nSize:  XL ")).toEqual([
      { name: "Color", value: "black", unit: null },
      { name: "Size", value: "XL", unit: null },
    ])
  })

  it("formats params with units back to lines", () => {
    const text = formatSellerLines([
      { name: "Width", value: "90", unit: "mm" },
      { name: "Color", value: "black", unit: null },
    ])
    expect(text).toBe("Width: 90 mm\nColor: black")
    expect(parseSellerLines(text)[0]).toEqual({ name: "Width", value: "90 mm", unit: null })
  })
})
