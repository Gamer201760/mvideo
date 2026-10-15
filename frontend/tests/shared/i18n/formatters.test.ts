import { describe, expect, it } from "vitest"
import { createFormatters } from "@/shared/i18n"

const SPACES = new RegExp(`[${String.fromCodePoint(0xa0, 0x202f)}]`, "g")
const plain = (text: string) => text.replace(SPACES, " ")

describe("formatters", () => {
  it("formats numbers and percents by locale", () => {
    expect(createFormatters("en").number(1234.5)).toBe("1,234.5")
    expect(plain(createFormatters("ru").number(1234.5))).toBe("1 234,5")
    expect(createFormatters("en").percent(0.427, 1)).toBe("42.7%")
    expect(plain(createFormatters("ru").percent(0.5))).toBe("50 %")
  })

  it("formats money and dates in a fixed time zone", () => {
    expect(createFormatters("en").money(12.5, "EUR")).toBe("€12.50")
    const date = Date.UTC(2026, 2, 14, 9, 30)
    expect(createFormatters("en", "UTC").date(date)).toBe("14 March 2026")
    expect(createFormatters("ru", "UTC").time(date)).toBe("09:30")
  })

  it("joins lists with the conjunction of the locale", () => {
    expect(createFormatters("en").list(["a", "b", "c"])).toBe("a, b and c")
  })
})
