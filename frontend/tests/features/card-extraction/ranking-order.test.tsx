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

  it("changes presentation order while preserving the real candidate set", () => {
    const { result } = renderHook(() => useRankingOrder(candidates, true, undefined))
    act(() => vi.advanceTimersByTime(2400))
    expect(ids(result.current)).not.toEqual(ids(candidates))
    expect([...ids(result.current)].sort()).toEqual(ids(candidates))
    expect(ids(candidates)).toEqual([1, 2, 3, 4, 5])
  })

  it("puts the actual selection first and stops reshuffling", () => {
    const { result, rerender } = renderHook(
      ({ pending, selected }: { pending: boolean; selected: number | undefined }) =>
        useRankingOrder(candidates, pending, selected),
      { initialProps: { pending: true, selected: undefined as number | undefined } },
    )
    act(() => vi.advanceTimersByTime(2400))
    rerender({ pending: false, selected: 4 })
    const selectedOrder = ids(result.current)
    expect(selectedOrder).toEqual([4, 1, 2, 3, 5])
    act(() => vi.advanceTimersByTime(10000))
    expect(ids(result.current)).toEqual(selectedOrder)
  })

  it("keeps retrieval order with reduced motion", () => {
    setReducedMotion(true)
    const { result } = renderHook(() => useRankingOrder(candidates, true, undefined))
    act(() => vi.advanceTimersByTime(10000))
    expect(ids(result.current)).toEqual(ids(candidates))
  })

  it("handles no candidates and a manual single category", () => {
    const { result, rerender } = renderHook(
      ({ rows }: { rows: readonly StandCategory[] | undefined }) =>
        useRankingOrder(rows, true, undefined),
      { initialProps: { rows: undefined as readonly StandCategory[] | undefined } },
    )
    expect(result.current).toEqual([])
    rerender({ rows: candidates.slice(0, 1) })
    act(() => vi.advanceTimersByTime(10000))
    expect(ids(result.current)).toEqual([1])
  })
})
