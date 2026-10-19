import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { CardForm } from "@/features/card-extraction/card-form/card-form"
import { readDraft, saveDraft } from "@/features/card-extraction/card-storage"
import { createI18n, type Locale, LocaleProvider } from "@/shared/i18n"

function setup(locale: Locale = "en") {
  const instance = createI18n(locale)
  const submit = vi.fn()
  render(
    <LocaleProvider instance={instance}>
      <CardForm categories={[]} examples={[]} pending={false} onSubmit={submit} />
    </LocaleProvider>,
  )
  return { user: userEvent.setup(), t: instance.t.bind(instance), submit }
}

describe("seller attribute validation", () => {
  it.each(["ru", "en"] as const)(
    "reports every invalid line in %s and submits all corrected attributes",
    async (locale) => {
      const { user, t, submit } = setup(locale)
      await user.type(screen.getByRole("textbox", { name: t("stand:form.titleField") }), "Phone")
      await user.click(screen.getByRole("button", { name: new RegExp(t("stand:form.details")) }))
      const seller = screen.getByRole("textbox", { name: t("stand:form.seller") })
      const raw = "Color: black\n\nBroken\n: value\nWidth:"
      await user.type(seller, raw)
      expect(screen.queryByRole("alert")).toBeNull()
      await user.tab()
      expect(screen.getByRole("alert").textContent).toContain(t("stand:form.sellerErrors.summary"))
      for (const [line, reason] of [
        [3, t("stand:form.sellerErrors.missingSeparator")],
        [4, t("stand:form.sellerErrors.missingName")],
        [5, t("stand:form.sellerErrors.missingValue")],
      ] as const) {
        expect(screen.getByText(t("stand:form.sellerErrors.line", { line, reason }))).toBeTruthy()
      }
      expect(seller.getAttribute("aria-invalid")).toBe("true")
      expect(seller.getAttribute("aria-describedby")).toContain(screen.getByRole("alert").id)
      await user.click(screen.getByRole("button", { name: t("stand:form.submit") }))
      expect(submit).not.toHaveBeenCalled()
      expect(document.activeElement).toBe(seller)
      expect(readDraft().seller).toBe(raw)
      await user.clear(seller)
      await user.type(seller, "Color: black\nWidth: 90 mm\nURL: https://example.com")
      expect(screen.queryByRole("alert")).toBeNull()
      expect(seller.hasAttribute("aria-invalid")).toBe(false)
      await user.click(screen.getByRole("button", { name: t("stand:form.submit") }))
      expect(submit).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({
          seller_params: [
            { name: "Color", value: "black", unit: null },
            { name: "Width", value: "90 mm", unit: null },
            { name: "URL", value: "https://example.com", unit: null },
          ],
        }),
      )
    },
  )

  it("opens a closed optional panel and focuses invalid input on the submit shortcut", async () => {
    const { user, t, submit } = setup()
    const title = screen.getByRole("textbox", { name: t("stand:form.titleField") })
    await user.type(title, "Phone")
    const details = screen.getByRole("button", { name: new RegExp(t("stand:form.details")) })
    await user.click(details)
    await user.type(screen.getByRole("textbox", { name: t("stand:form.seller") }), "Bad")
    details.focus()
    await user.keyboard("{Enter}")
    expect(details.getAttribute("aria-expanded")).toBe("false")
    title.focus()
    await user.keyboard("{Control>}{Enter}{/Control}")
    expect(details.getAttribute("aria-expanded")).toBe("true")
    expect(document.activeElement).toBe(
      screen.getByRole("textbox", { name: t("stand:form.seller") }),
    )
    expect(submit).not.toHaveBeenCalled()
    expect(screen.getByRole("alert")).toBeTruthy()
  })

  it("restores invalid draft text without losing lines", () => {
    const raw = "Width: \nBroken\nColor: black"
    saveDraft({ title: "Phone", description: "", seller: raw, engine: "hybrid", category: null })
    const { t } = setup()
    const seller = screen.getByRole("textbox", { name: t("stand:form.seller") })
    expect((seller as HTMLTextAreaElement).value).toBe(raw)
    expect(screen.getByRole("alert")).toBeTruthy()
  })

  it("submits when optional seller attributes are empty", async () => {
    const { user, t, submit } = setup()
    await user.type(screen.getByRole("textbox", { name: t("stand:form.titleField") }), "Phone")
    await user.click(screen.getByRole("button", { name: t("stand:form.submit") }))
    expect(submit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ seller_params: [] }))
  })
})
