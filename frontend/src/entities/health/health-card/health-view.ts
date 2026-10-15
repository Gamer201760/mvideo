import type { LoadingIndicator } from "@/shared/motion"

export type HealthView = "waiting" | "loading" | "error" | "ok"

export interface HealthQueryState {
  readonly isError: boolean
  readonly hasData: boolean
}

export function healthView(query: HealthQueryState, indicator: LoadingIndicator): HealthView {
  if (indicator === "skeleton") return "loading"
  if (query.isError) return "error"
  return query.hasData ? "ok" : "waiting"
}
