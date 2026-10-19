import { useEffect, useState } from "react"
import type { StandCategory } from "@/entities/stand"
import { motionMs, useReducedMotion } from "@/shared/motion"

export function useRankingOrder(
  candidates: readonly StandCategory[] | undefined,
  pending: boolean,
  selected: number | null | undefined,
) {
  const reduced = useReducedMotion()
  const [step, setStep] = useState(0)
  const count = candidates?.length ?? 0
  useEffect(() => {
    if (!pending || selected !== undefined || count < 2 || reduced) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setStep((value) => value + 1)
    }, motionMs("--dur-breathe"))
    return () => window.clearInterval(timer)
  }, [pending, selected, count, reduced])

  const ordered = [...(candidates ?? [])]
  if (selected != null) {
    ordered.sort((a, b) => Number(b.category_id === selected) - Number(a.category_id === selected))
  } else if (!reduced && ordered.length > 1) {
    const phases = step % (ordered.length * 2)
    for (let index = 0; index < phases; index += 1) {
      const pair = index % (ordered.length - 1)
      const first = ordered[pair]
      const second = ordered[pair + 1]
      if (first !== undefined && second !== undefined) {
        ordered[pair] = second
        ordered[pair + 1] = first
      }
    }
  }
  return ordered
}
