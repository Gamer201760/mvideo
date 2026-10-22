import type { StandCategory } from "@/entities/stand"

export function useRankingOrder(candidates: readonly StandCategory[] | undefined) {
  return candidates ?? []
}
