import {
  createContext,
  type ReactNode,
  useCallback,
  useLayoutEffect,
  useMemo,
  useState,
} from "react"
import { useMediaQuery } from "@/shared/hooks"
import {
  applyTheme,
  DARK_QUERY,
  readStoredTheme,
  storeTheme,
  systemTheme,
  type Theme,
} from "./theme"

export interface ThemeState {
  readonly theme: Theme
  readonly setTheme: (theme: Theme) => void
}

export const ThemeContext = createContext<ThemeState | null>(null)

export interface ThemeProviderProps {
  readonly children: ReactNode
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [stored, setStored] = useState<Theme | null>(readStoredTheme)
  const systemDark = useMediaQuery(DARK_QUERY)
  const theme = stored ?? systemTheme(systemDark)

  useLayoutEffect(() => {
    applyTheme(theme)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    storeTheme(next)
    setStored(next)
  }, [])

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])
  return <ThemeContext value={value}>{children}</ThemeContext>
}
