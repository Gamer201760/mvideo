import { ApiError, kindOf, NETWORK_UNAVAILABLE } from "@/shared/api"
import type { MessageKey } from "./i18next"

type KeyExists = (key: string) => boolean

function resolve(error: unknown, group: string, kindGroup: string, exists: KeyExists): MessageKey {
  const code = error instanceof ApiError ? error.code : NETWORK_UNAVAILABLE
  const kind = error instanceof ApiError ? error.kind : kindOf(0)
  const specific = `errors:${group}.${code}`
  if (exists(specific)) return specific as MessageKey
  return `errors:${kindGroup}.${kind}` as MessageKey
}

export function errorMessageKey(error: unknown, exists: KeyExists): MessageKey {
  return resolve(error, "api", "kind", exists)
}

export function errorHeadlineKey(error: unknown, exists: KeyExists): MessageKey {
  return resolve(error, "headline", "headline", exists)
}
