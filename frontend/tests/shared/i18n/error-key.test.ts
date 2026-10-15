import { describe, expect, it } from "vitest"
import { ApiError, NETWORK_UNAVAILABLE } from "@/shared/api"
import { errorMessageKey } from "@/shared/i18n"

describe("errorMessageKey", () => {
  const known = new Set(["errors:api.server_unavailable"])
  const exists = (key: string) => known.has(key)

  it("prefers the code key, then the kind key", () => {
    expect(errorMessageKey(new ApiError(503, "server_unavailable"), exists)).toBe(
      "errors:api.server_unavailable",
    )
    expect(errorMessageKey(new ApiError(404, "order_missing"), exists)).toBe("errors:kind.notFound")
    expect(errorMessageKey(new ApiError(418, "teapot"), exists)).toBe("errors:kind.unknown")
  })

  it("treats unknown errors as a lost connection", () => {
    expect(errorMessageKey(new TypeError("Failed to fetch"), exists)).toBe("errors:kind.network")
    expect(errorMessageKey(new ApiError(0, NETWORK_UNAVAILABLE), exists)).toBe(
      "errors:kind.network",
    )
  })
})
