import { useMutation } from "@tanstack/react-query"
import { api, unwrap } from "@/shared/api"
import { reconcileReviews } from "./review-result"
import type { ExtractInput, ExtractResult, ReviewItem } from "./stand.queries"

export type CardExportSource =
  | { readonly runId: string }
  | { readonly input: ExtractInput; readonly result: ExtractResult }

export interface CardExport {
  readonly schema_version: 1
  readonly input: ExtractInput
  readonly result: ExtractResult
  readonly decisions: readonly ReviewItem[]
}

async function prepareExport(source: CardExportSource): Promise<CardExport> {
  const { input, result } =
    "runId" in source
      ? await unwrap(
          api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: source.runId } } }),
        )
      : source
  if (result === null) throw new Error("Extraction has no completed result")
  const reviews = await unwrap(
    api.POST("/api/v1/review/card", {
      body: { ...input, category_id: result.category?.category_id ?? input.category_id ?? null },
    }),
  )
  return {
    schema_version: 1,
    input,
    result: reconcileReviews(result, reviews.items),
    decisions: reviews.items.filter(
      (item) =>
        item.status === "accepted" || item.status === "corrected" || item.status === "rejected",
    ),
  }
}

export function useCardExport() {
  return useMutation({ mutationFn: prepareExport })
}
