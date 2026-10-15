import { describe, expect, it } from "vitest"
import {
  ApiError,
  codeOf,
  isApiError,
  kindOf,
  NETWORK_UNAVAILABLE,
  shouldRetry,
  UNEXPECTED,
  unwrap,
} from "@/shared/api"

const response = (status: number) => new Response(null, { status })

describe("ApiError", () => {
  it.each([
    [0, "network"],
    [401, "auth"],
    [403, "forbidden"],
    [404, "notFound"],
    [409, "conflict"],
    [422, "validation"],
    [503, "server"],
    [418, "unknown"],
  ])("maps status %i to kind %s", (status, kind) => {
    expect(kindOf(status)).toBe(kind)
    expect(new ApiError(status, "x").kind).toBe(kind)
  })

  it("takes the code from the body and never from the message", () => {
    expect(codeOf({ code: "order_locked", message: "Locked" })).toBe("order_locked")
    expect(codeOf({ detail: "Not found" })).toBe(UNEXPECTED)
    expect(codeOf(null)).toBe(UNEXPECTED)
  })
})

describe("unwrap", () => {
  it("returns data of a successful response", async () => {
    await expect(
      unwrap(Promise.resolve({ data: { ok: 1 }, response: response(200) })),
    ).resolves.toEqual({ ok: 1 })
  })

  it("throws ApiError with the backend code", async () => {
    const failed = unwrap(
      Promise.resolve({ error: { code: "order_locked" }, response: response(409) }),
    )
    await expect(failed).rejects.toMatchObject({
      status: 409,
      code: "order_locked",
      kind: "conflict",
    })
  })

  it("turns a failed fetch into a network error", async () => {
    const error = await unwrap(Promise.reject(new TypeError("Failed to fetch"))).catch(
      (caught: unknown) => caught,
    )
    expect(isApiError(error, NETWORK_UNAVAILABLE)).toBe(true)
  })
})

describe("shouldRetry", () => {
  it("retries server and network errors twice, client errors never", () => {
    expect(shouldRetry(0, new ApiError(404, "x"))).toBe(false)
    expect(shouldRetry(1, new ApiError(503, "x"))).toBe(true)
    expect(shouldRetry(1, new ApiError(0, NETWORK_UNAVAILABLE))).toBe(true)
    expect(shouldRetry(2, new ApiError(503, "x"))).toBe(false)
  })
})
