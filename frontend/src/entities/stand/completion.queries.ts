import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api, unwrap } from "@/shared/api"
import type { components } from "@/shared/api/schema.gen"
import { publishReviewChange } from "./review-sync"
import { standKeys } from "./stand.queries"

type AddInput = components["schemas"]["AddReviewRequest"]

export function useAddAttribute() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: AddInput) => unwrap(api.POST("/api/v1/review/add", { body })),
    onSuccess: () => {
      publishReviewChange()
      return client.invalidateQueries({ queryKey: standKeys.review })
    },
  })
}
