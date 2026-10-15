import type { i18n as I18nInstance } from "i18next"
import { createContext, type ReactNode, useCallback, useEffect, useMemo, useState } from "react"
import { I18nextProvider } from "react-i18next"
import { documentTitle } from "./document-title"
import { i18n as defaultInstance } from "./instance"
import { DEFAULT_LOCALE, isLocale, type Locale, storeLocale } from "./locale"
import { NAMESPACES } from "./resources"

export interface LocaleState {
  readonly locale: Locale
  readonly setLocale: (locale: Locale) => void
  readonly setPageTitle: (title: string | null) => void
}

export const LocaleContext = createContext<LocaleState | null>(null)

export interface LocaleProviderProps {
  readonly children: ReactNode
  readonly instance?: I18nInstance
}

function currentLocale(instance: I18nInstance): Locale {
  const language = instance.resolvedLanguage ?? instance.language
  return isLocale(language) ? language : DEFAULT_LOCALE
}

export function LocaleProvider({ children, instance = defaultInstance }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(() => currentLocale(instance))
  const [pageTitle, setPageTitle] = useState<string | null>(null)

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    storeLocale(next)
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale
    if (instance.language !== locale) void instance.changeLanguage(locale)
    const t = instance.getFixedT(locale, NAMESPACES)
    document.title = documentTitle(t("common:app.name"), t("common:app.tagline"), pageTitle)
  }, [instance, locale, pageTitle])

  const value = useMemo(() => ({ locale, setLocale, setPageTitle }), [locale, setLocale])

  return (
    <I18nextProvider i18n={instance}>
      <LocaleContext value={value}>{children}</LocaleContext>
    </I18nextProvider>
  )
}
