import { describe, expect, it } from "vitest"
import { healthView } from "@/entities/health/health-card/health-view"

describe("healthView", () => {
  it("holds the skeleton while the loading indicator asks for it", () => {
    expect(healthView({ isError: true, hasData: false }, "skeleton")).toBe("loading")
  })

  it("shows the error, the data or nothing yet", () => {
    expect(healthView({ isError: true, hasData: false }, "none")).toBe("error")
    expect(healthView({ isError: false, hasData: true }, "stale")).toBe("ok")
    expect(healthView({ isError: false, hasData: false }, "none")).toBe("waiting")
  })
})
