import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { RejectedFields } from "@/features/card-extraction/rejected-fields/rejected-fields"
import { createI18n, LocaleProvider } from "@/shared/i18n"

describe("RejectedFields", () => {
  it.each(["ru", "en"] as const)(
    "explains the omission with the original quote in %s",
    (locale) => {
      const instance = createI18n(locale)
      render(
        <LocaleProvider instance={instance}>
          <RejectedFields
            rejections={[
              { attribute: "NFC", reason: "field_mismatch", evidence: "Bluetooth: Yes" },
            ]}
          />
        </LocaleProvider>,
      )
      expect(
        screen.getByRole("region", { name: instance.t("stand:rejections.title") }),
      ).toBeTruthy()
      expect(screen.getByText("NFC")).toBeTruthy()
      expect(screen.getByText(instance.t("stand:rejections.otherField"))).toBeTruthy()
      expect(screen.getByRole("blockquote").textContent).toBe("Bluetooth: Yes")
    },
  )

  it("handles responses saved before rejection details were added", () => {
    const instance = createI18n("ru")
    render(
      <LocaleProvider instance={instance}>
        <RejectedFields rejections={undefined} />
      </LocaleProvider>,
    )
    expect(screen.queryByRole("region")).toBeNull()
  })
})
