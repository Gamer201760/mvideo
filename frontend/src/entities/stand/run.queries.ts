import { useMutation, useQuery } from "@tanstack/react-query"
import { api, unwrap } from "@/shared/api"
import type { components } from "@/shared/api/schema.gen"

export type RunDetail = components["schemas"]["RunDetailResponse"]
export type RunSummary = components["schemas"]["RunSummarySchema"]
export const RUN_PAGE_SIZE = 20
export const runKeys = { all: ["stand", "runs"] as const }

export function useRuns(offset: number) {
  return useQuery({
    queryKey: [...runKeys.all, offset],
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/runs", { params: { query: { offset, limit: RUN_PAGE_SIZE } }, signal }),
      ),
    refetchInterval: 5000,
  })
}

export function useOpenRun() {
  return useMutation({
    mutationFn: (run_id: string) =>
      unwrap(api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id } } })),
  })
}
