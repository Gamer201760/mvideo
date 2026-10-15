import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { CardText, type ExtractedValue } from "@/entities/stand"

function value(attribute: string, start: number, end: number, status: "accepted" | "review") {
  const item: ExtractedValue = {
    attribute,
    value: attribute,
    confidence: 0.5,
    source: "dictionary",
    sources: ["dictionary"],
    evidence: "",
    start,
    end,
    status,
    review_id: null,
  }
  return item
}

describe("CardText", () => {
  it("marks quote spans and skips overlapping or out of range spans", () => {
    const text = "Phone Samsung black 128 GB"
    const { container } = render(
      <CardText
        text={text}
        activeAttribute="Brand"
        values={[
          value("Brand", 6, 13, "accepted"),
          value("Model", 6, 19, "review"),
          value("Color", 14, 19, "review"),
          value("Broken", 20, 99, "accepted"),
        ]}
      />,
    )
    const marks = [...container.querySelectorAll("mark")]
    expect(marks.map((m) => m.textContent)).toEqual(["Samsung black"])
    expect(container.textContent).toBe(text)
  })

  it("keeps status and focus on each mark", () => {
    const { container } = render(
      <CardText
        text="Phone Samsung black"
        activeAttribute="Color"
        values={[value("Brand", 6, 13, "accepted"), value("Color", 14, 19, "review")]}
      />,
    )
    const marks = [...container.querySelectorAll("mark")]
    expect(marks.map((m) => [m.dataset.status, m.dataset.active])).toEqual([
      ["accepted", "false"],
      ["review", "true"],
    ])
  })
})
