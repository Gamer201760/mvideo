import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { ExtractedValue } from "@/entities/stand"
import { useInlineReview } from "@/features/card-extraction/inline-review/use-inline-review"
import { createI18n, LocaleProvider } from "@/shared/i18n"

function ReviewControls({
  value,
  manualMode,
}: {
  readonly value: ExtractedValue
  readonly manualMode: boolean
}) {
  const slots = useInlineReview(undefined, false, manualMode)
  return (
    <>
      {slots.value(value)}
      {slots.actions(value)}
    </>
  )
}

function showControls(score: number | null, confidence: number, manualMode = false) {
  const value: ExtractedValue = {
    attribute: "Brand",
    value: "North",
    confidence,
    source: "hybrid",
    sources: ["hybrid"],
    evidence: "North",
    start: 0,
    end: 5,
    status: "review",
    review_id: "brand",
    risk:
      score === null
        ? null
        : {
            score,
            level: "low",
            reasons: ["exact_quote"],
            method: "heuristic",
          },
  }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LocaleProvider instance={createI18n("en")}>
        <ReviewControls value={value} manualMode={manualMode} />
      </LocaleProvider>
    </QueryClientProvider>,
  )
}

describe("inline review confirmation", () => {
  it.each([
    [1, 0.8],
    [0.999, 0.8],
    [null, 1],
  ] as const)(
    "hides confirmation for a displayed full score and keeps manual editing: %s, %s",
    (score, confidence) => {
      showControls(score, confidence)
      expect(screen.queryByRole("button", { name: "Confirm value: Brand" })).toBeNull()
      expect(screen.queryByRole("button", { name: "Edit manually: Brand" })).toBeNull()
      expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("North")
    },
  )

  it("keeps confirmation for a lower displayed score", () => {
    showControls(0.85, 1)
    expect(screen.getByRole("button", { name: "Confirm value: Brand" })).toBeTruthy()
  })

  it("allows confirmation of a full score when automatic acceptance is disabled", () => {
    showControls(1, 1, true)
    expect(screen.getByRole("button", { name: "Confirm value: Brand" })).toBeTruthy()
  })
})
