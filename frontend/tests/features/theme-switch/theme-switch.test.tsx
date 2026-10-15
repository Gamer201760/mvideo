import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { ThemeSwitch } from "@/features/theme-switch"
import { createI18n, LocaleProvider } from "@/shared/i18n"
import ru from "@/shared/i18n/locales/ru/common.json"
import { THEME_STORAGE_KEY, ThemeProvider } from "@/shared/theme"

function renderSwitch() {
  return render(
    <LocaleProvider instance={createI18n("ru")}>
      <ThemeProvider>
        <ThemeSwitch />
      </ThemeProvider>
    </LocaleProvider>,
  )
}

describe("ThemeSwitch", () => {
  it("follows the system theme until a choice is made, without a system option", () => {
    renderSwitch()
    expect(screen.getAllByRole("radio")).toHaveLength(2)
    expect((screen.getByRole("radio", { name: ru.theme.light }) as HTMLInputElement).checked).toBe(
      true,
    )
    expect(document.documentElement.dataset.theme).toBe("light")
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })

  it("applies and stores the chosen theme", async () => {
    renderSwitch()
    await userEvent.click(screen.getByRole("radio", { name: ru.theme.dark }))
    expect(document.documentElement.dataset.theme).toBe("dark")
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark")
  })

  it("restores the stored choice", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark")
    renderSwitch()
    expect((screen.getByRole("radio", { name: ru.theme.dark }) as HTMLInputElement).checked).toBe(
      true,
    )
    expect(document.documentElement.dataset.theme).toBe("dark")
  })
})
