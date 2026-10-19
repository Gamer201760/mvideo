import { useCallback } from "react"
import { errorHeadlineKey, errorMessageKey } from "./error-key"
import { useTranslation } from "./use-translation"

export interface ErrorCopy {
  readonly title: string
  readonly description: string
}

export function useErrorCopy(): (error: unknown) => ErrorCopy {
  const { t, i18n } = useTranslation()
  return useCallback(
    (error: unknown) => {
      const exists = (key: string) => i18n.exists(key)
      return {
        title: t(errorHeadlineKey(error, exists)),
        description: t(errorMessageKey(error, exists)),
      }
    },
    [t, i18n],
  )
}
