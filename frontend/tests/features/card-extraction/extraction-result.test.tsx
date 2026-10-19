import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ExtractResult } from "@/entities/stand"
import { ExtractionResult } from "@/features/card-extraction/extraction-result/extraction-result"
import { createI18n, LocaleProvider } from "@/shared/i18n"
import {
  applyMotionTokens,
  resetMotionEnvironment,
  setReducedMotion,
} from "../../setup/motionEnvironment"

describe("extraction completeness", () => {
  beforeEach(() => {
    applyMotionTokens()
    setReducedMotion(true)
  })
  afterEach(resetMotionEnvironment)
  it.each([
    ["ru", "rejected"],
    ["en", "rejected"],
    ["ru", "unknown"],
    ["en", "unknown"],
    ["ru", "empty"],
    ["en", "empty"],
  ] as const)("does not claim completeness in %s for %s", (locale, state) => {
    const instance = createI18n(locale)
    const result: ExtractResult = {
      engine: "hybrid",
      threshold: 0.95,
      auto_accept_enabled: true,
      text: "Glasses with a 12 MP camera",
      category:
        state === "unknown"
          ? null
          : {
              category_id: -2,
              name: "Glasses",
              path: "Wearables / Glasses",
              attributes: [],
            },
      missing: [],
      values: [],
      extra_values: [],
      rejections:
        state === "empty"
          ? []
          : [
              {
                attribute: "Camera resolution",
                reason: "field_unconfirmed",
                evidence: "12 MP camera",
              },
            ],
    }
    render(
      <LocaleProvider instance={instance}>
        <ExtractionResult result={result} pending={false} error={null} onRetry={vi.fn()} />
      </LocaleProvider>,
    )
    expect(screen.queryByText(instance.t("stand:result.missingNone"))).toBeNull()
    const key =
      state === "unknown"
        ? "stand:result.categoryUnknown"
        : state === "empty"
          ? "stand:result.requiredUnknown"
          : "stand:result.missingUnconfirmed"
    expect(screen.getByText(instance.t(key))).toBeTruthy()
    if (state !== "empty") expect(screen.getByRole("blockquote").textContent).toBe("12 MP camera")
  })
})
