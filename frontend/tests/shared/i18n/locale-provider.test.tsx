import { act, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import {
  createI18n,
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  useDocumentTitle,
  useLocale,
  useTranslation,
} from "@/shared/i18n"
import en from "@/shared/i18n/locales/en/common.json"
import ru from "@/shared/i18n/locales/ru/common.json"

function Probe({ page }: { readonly page: string | null }) {
  const { t } = useTranslation()
  useDocumentTitle(page)
  const { locale, setLocale } = useLocale()
  return (
    <button type="button" data-locale={locale} onClick={() => setLocale("en")}>
      {t("common:action.retry")}
    </button>
  )
}

function renderProbe(page: string | null = null) {
  return render(
    <LocaleProvider instance={createI18n()}>
      <Probe page={page} />
    </LocaleProvider>,
  )
}

function setLanguages(languages: readonly string[]) {
  Object.defineProperty(navigator, "languages", { value: languages, configurable: true })
}

describe("LocaleProvider", () => {
  it("renders russian by default and sets the document language and title", () => {
    setLanguages(["ru-RU"])
    renderProbe()
    expect(screen.getByRole("button").textContent).toBe(ru.action.retry)
    expect(document.documentElement.lang).toBe("ru")
    expect(document.title).toBe(`${ru.app.name} | ${ru.app.tagline}`)
  })

  it("puts the page title into the tab title in the current language", async () => {
    setLanguages(["ru-RU"])
    renderProbe("Orders")
    expect(document.title).toBe(`Orders | ${ru.app.name}`)
    await act(async () => screen.getByRole("button").click())
    expect(document.title).toBe(`Orders | ${en.app.name}`)
  })

  it("switches language, stores the choice and updates lang", async () => {
    renderProbe()
    await act(async () => screen.getByRole("button").click())
    expect(screen.getByRole("button").textContent).toBe(en.action.retry)
    expect(document.documentElement.lang).toBe("en")
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en")
  })

  it("restores the stored locale before the browser language", () => {
    setLanguages(["ru-RU"])
    localStorage.setItem(LOCALE_STORAGE_KEY, "en")
    renderProbe()
    expect(screen.getByRole("button").textContent).toBe(en.action.retry)
  })

  it("falls back to the browser language, then to russian", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "de")
    setLanguages(["en-US"])
    const { unmount } = renderProbe()
    expect(screen.getByRole("button").dataset.locale).toBe("en")
    unmount()
    setLanguages(["de-DE"])
    renderProbe()
    expect(screen.getByRole("button").dataset.locale).toBe("ru")
  })
})
