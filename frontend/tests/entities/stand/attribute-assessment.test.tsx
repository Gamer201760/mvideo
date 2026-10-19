import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { ExtractedValue } from "@/entities/stand"
import { AttributeAssessment } from "@/entities/stand/attribute-table/attribute-assessment"
import { createI18n, LocaleProvider } from "@/shared/i18n"

const value: ExtractedValue = {
  attribute: "Volume",
  value: "1.7",
  confidence: null,
  source: "hybrid",
  sources: ["hybrid"],
  evidence: "1700 ml",
  start: 0,
  end: 7,
  status: "unverified",
  review_id: null,
  risk: {
    level: "high",
    score: 0.99,
    reasons: ["range_lost", "exact_quote", "value_supported", "number_supported", "category_field"],
    method: "catalog_proxy",
  },
}

describe("AttributeAssessment", () => {
  it("shows support points and risk reasons without a correctness percentage", () => {
    const instance = createI18n("ru")
    render(
      <LocaleProvider instance={instance}>
        <AttributeAssessment value={value} />
      </LocaleProvider>,
    )
    expect(screen.getByText(instance.t("stand:risk.score", { value: 99, max: 100 }))).toBeTruthy()
    expect(screen.getByText(instance.t("stand:risk.high"))).toBeTruthy()
    expect(
      screen.getByText(instance.t("stand:risk.reasons.range_lost"), { exact: false }),
    ).toBeTruthy()
    for (const reason of [
      "exact_quote",
      "value_supported",
      "number_supported",
      "category_field",
    ] as const)
      expect(
        screen.getByText(instance.t(`stand:risk.reasons.${reason}`), { exact: false }),
      ).toBeTruthy()
    expect(screen.queryByText(/99\s*%/)).toBeNull()
  })
})
