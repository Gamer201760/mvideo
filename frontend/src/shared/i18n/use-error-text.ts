import { useCallback } from "react"
import { errorMessageKey } from "./error-key"
import { useTranslation } from "./use-translation"

export function useErrorText(): (error: unknown) => string {
  const { t, i18n } = useTranslation()
  return useCallback(
    (error: unknown) => t(errorMessageKey(error, (key) => i18n.exists(key))),
    [t, i18n],
  )
}
