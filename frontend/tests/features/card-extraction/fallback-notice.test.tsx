import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { FallbackNotice } from "@/features/card-extraction/fallback-notice/fallback-notice"
import { createI18n, LocaleProvider } from "@/shared/i18n"

describe("gateway fallback disclosure", () => {
  it.each(["ru", "en"] as const)("explains local extraction in %s", (locale) => {
    const instance = createI18n(locale)
    render(
      <LocaleProvider instance={instance}>
        <FallbackNotice reason="model_unavailable" />
      </LocaleProvider>,
    )
    const notice = screen.getByRole("status")
    expect(notice.textContent).toContain(instance.t("stand:result.fallbackTitle"))
    expect(notice.textContent).toContain(instance.t("stand:result.fallbackDescription"))
    expect(notice.textContent).not.toContain("model_unavailable")
  })

  it.each([undefined, null, ""])("keeps ordinary and old results unchanged for %s", (reason) => {
    render(
      <LocaleProvider instance={createI18n("ru")}>
        <FallbackNotice reason={reason} />
      </LocaleProvider>,
    )
    expect(screen.queryByRole("status")).toBeNull()
  })
})
