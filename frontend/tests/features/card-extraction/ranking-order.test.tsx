import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { StandCategory } from "@/entities/stand"
import { useRankingOrder } from "@/features/card-extraction/extraction-progress/use-ranking-order"
import { applyMotionTokens, setReducedMotion } from "../../setup/motionEnvironment"

const candidates: readonly StandCategory[] = Array.from({ length: 5 }, (_, index) => ({
  category_id: index + 1,
  name: String(index),
  path: String(index),
  attributes: [],
}))

const ids = (rows: readonly StandCategory[]) => rows.map((row) => row.category_id)

describe("useRankingOrder", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    applyMotionTokens()
    setReducedMotion(false)
  })
  afterEach(() => vi.useRealTimers())

  it("preserves the API ranking during waiting", () => {
    const { result } = renderHook(() => useRankingOrder(candidates))
    act(() => vi.advanceTimersByTime(2400))
    expect(ids(result.current)).toEqual(ids(candidates))
    expect([...ids(result.current)].sort()).toEqual(ids(candidates))
    expect(ids(candidates)).toEqual([1, 2, 3, 4, 5])
  })

  it("follows a fresh API ranking without inventing positions", () => {
    const { result, rerender } = renderHook(({ rows }) => useRankingOrder(rows), {
      initialProps: { rows: candidates },
    })
    rerender({ rows: [...candidates].reverse() })
    expect(ids(result.current)).toEqual([5, 4, 3, 2, 1])
  })

  it("keeps retrieval order with reduced motion", () => {
    setReducedMotion(true)
    const { result } = renderHook(() => useRankingOrder(candidates))
    act(() => vi.advanceTimersByTime(10000))
    expect(ids(result.current)).toEqual(ids(candidates))
  })

  it("handles no candidates and a manual single category", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly StandCategory[] | undefined }) => useRankingOrder(rows),
      { initialProps: { rows: undefined as readonly StandCategory[] | undefined } },
    )
    expect(result.current).toEqual([])
    rerender({ rows: candidates.slice(0, 1) })
    act(() => vi.advanceTimersByTime(10000))
    expect(ids(result.current)).toEqual([1])
  })
})
