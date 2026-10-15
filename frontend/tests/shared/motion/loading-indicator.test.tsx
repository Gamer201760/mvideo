import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { type LoadingInput, useLoadingIndicator } from "@/shared/motion"
import { applyMotionTokens } from "../../setup/motionEnvironment"

function renderIndicator(initial: LoadingInput) {
  return renderHook((input: LoadingInput) => useLoadingIndicator(input), { initialProps: initial })
}

describe("useLoadingIndicator", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    applyMotionTokens()
  })
  afterEach(() => vi.useRealTimers())

  it("shows nothing for fast answers", () => {
    const { result, rerender } = renderIndicator({ pending: true, hasData: false })
    act(() => vi.advanceTimersByTime(150))
    rerender({ pending: false, hasData: true })
    expect(result.current).toBe("none")
  })

  it("shows the skeleton after 200ms and holds it for 300ms", () => {
    const { result, rerender } = renderIndicator({ pending: true, hasData: false })
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe("skeleton")
    rerender({ pending: false, hasData: true })
    act(() => vi.advanceTimersByTime(250))
    expect(result.current).toBe("skeleton")
    act(() => vi.advanceTimersByTime(60))
    expect(result.current).toBe("none")
  })

  it("dims existing data first and adds a spinner after 400ms", () => {
    const { result } = renderIndicator({ pending: true, hasData: true })
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe("stale")
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe("spinner")
  })
})
