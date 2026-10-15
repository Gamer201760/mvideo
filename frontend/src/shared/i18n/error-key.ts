import { ApiError, kindOf, NETWORK_UNAVAILABLE } from "@/shared/api"
import type { MessageKey } from "./i18next"

export function errorMessageKey(error: unknown, exists: (key: string) => boolean): MessageKey {
  const code = error instanceof ApiError ? error.code : NETWORK_UNAVAILABLE
  const kind = error instanceof ApiError ? error.kind : kindOf(0)
  const specific = `errors:api.${code}`
  if (exists(specific)) return specific as MessageKey
  return `errors:kind.${kind}` as MessageKey
}
