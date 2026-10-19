import { useEffect, useState } from "react"
import { motionMs, withViewTransition } from "@/shared/motion"

type SelectionStage = "ranking" | "selected" | "complete"

export function useSelectionReveal(count: number | undefined, resolved: boolean): SelectionStage {
  const [ranked, setRanked] = useState(false)
  const [stage, setStage] = useState<SelectionStage>("ranking")
  useEffect(() => {
    if (count === undefined) return
    const timer = window.setTimeout(
      () => setRanked(true),
      Math.max(0, count - 1) * motionMs("--dur-slow") + motionMs("--dur-draw"),
    )
    return () => window.clearTimeout(timer)
  }, [count])
  useEffect(() => {
    if (!ranked || !resolved) return
    setStage("selected")
    const timer = window.setTimeout(
      () => void withViewTransition("stage", () => setStage("complete")),
      motionMs("--dur-draw"),
    )
    return () => window.clearTimeout(timer)
  }, [ranked, resolved])
  return stage
}
