export const THEMES = ["light", "dark"] as const

export type Theme = (typeof THEMES)[number]

export const THEME_STORAGE_KEY = "app-theme"

export const DARK_QUERY = "(prefers-color-scheme: dark)"

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value)
}

export function readStoredTheme(): Theme | null {
  try {
    const stored = globalThis.localStorage?.getItem(THEME_STORAGE_KEY)
    return isTheme(stored) ? stored : null
  } catch {
    return null
  }
}

export function storeTheme(theme: Theme): void {
  try {
    globalThis.localStorage?.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    return
  }
}

export function systemTheme(systemDark: boolean): Theme {
  return systemDark ? "dark" : "light"
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}
