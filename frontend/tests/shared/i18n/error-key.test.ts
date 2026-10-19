import { describe, expect, it } from "vitest"
import { ApiError, NETWORK_UNAVAILABLE } from "@/shared/api"
import { errorHeadlineKey, errorMessageKey } from "@/shared/i18n"

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

  it("resolves the headline the same way as the message", () => {
    const headlines = new Set(["errors:headline.stand_unavailable"])
    const has = (key: string) => headlines.has(key)
    expect(errorHeadlineKey(new ApiError(503, "stand_unavailable"), has)).toBe(
      "errors:headline.stand_unavailable",
    )
    expect(errorHeadlineKey(new ApiError(500, "boom"), has)).toBe("errors:headline.server")
    expect(errorHeadlineKey(new TypeError("Failed to fetch"), has)).toBe("errors:headline.network")
  })
})
