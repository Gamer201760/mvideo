import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { ExtractedValue } from "@/entities/stand"
import { AttributeTable } from "@/entities/stand/attribute-table/attribute-table"
import { createI18n, LocaleProvider } from "@/shared/i18n"

function value(attribute: string, status: ExtractedValue["status"]): ExtractedValue {
  return {
    attribute,
    status,
    value: attribute,
    confidence: null,
    source: "hybrid",
    sources: ["hybrid"],
    evidence: attribute,
    start: 0,
    end: attribute.length,
    review_id: null,
    risk: null,
  }
}

function attributes(): string[] {
  return within(screen.getByRole("table"))
    .getAllByRole("rowheader")
    .map((element) => element.textContent ?? "")
}

describe("AttributeTable", () => {
  it("prioritizes pending decisions and moves confirmed values below them", () => {
    const instance = createI18n("en")
    const values = [value("Brand", "accepted"), value("Color", "review"), value("Size", "review")]
    const table = (items: readonly ExtractedValue[]) => (
      <LocaleProvider instance={instance}>
        <AttributeTable values={items} onFocusAttribute={() => undefined} />
      </LocaleProvider>
    )
    const { rerender } = render(table(values))
    expect(attributes()).toEqual(["Color", "Size", "Brand"])
    expect(values.map((item) => item.attribute)).toEqual(["Brand", "Color", "Size"])
    rerender(
      table([values[0] as ExtractedValue, value("Color", "accepted"), values[2] as ExtractedValue]),
    )
    expect(attributes()).toEqual(["Size", "Brand", "Color"])
  })
})
