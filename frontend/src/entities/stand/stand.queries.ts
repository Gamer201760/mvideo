import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, unwrap } from "@/shared/api"
import type { components } from "@/shared/api/schema.gen"

type Schemas = components["schemas"]

export type StandInfo = Schemas["StandInfoResponse"]
export type StandCategory = Schemas["CategorySchema"]
export type StandExample = Schemas["ExampleSchema"]
export type SellerParam = Schemas["SellerParamSchema"]
export type ExtractInput = Schemas["ExtractRequest"]
export type ExtractResult = Schemas["ExtractResponse"]
export type ExtractedValue = Schemas["ExtractedValueSchema"]
export type ReviewItem = Schemas["ReviewItemSchema"]
export type ReviewAction = Schemas["ResolveRequest"]["action"]
export type TextInput = Schemas["ExtractTextRequest"]
export type TextResult = Schemas["ExtractTextResponse"]
export type TextValue = Schemas["TextValueSchema"]

export const standKeys = {
  info: ["stand", "info"] as const,
  examples: ["stand", "examples"] as const,
  review: ["stand", "review"] as const,
}

export function useStandInfo() {
  return useQuery({
    queryKey: standKeys.info,
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/stand", { signal })),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useExamples() {
  return useQuery({
    queryKey: standKeys.examples,
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/examples", { signal })),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useExtract() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: ExtractInput) => unwrap(api.POST("/api/v1/extract", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: standKeys.review }),
  })
}

export function useExtractText() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: TextInput) => unwrap(api.POST("/api/v1/extract-text", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: standKeys.review }),
  })
}

export function useReviewQueue() {
  return useQuery({
    queryKey: standKeys.review,
    queryFn: ({ signal }) =>
      unwrap(api.GET("/api/v1/review", { params: { query: { status: "pending" } }, signal })),
  })
}

export interface ResolveInput {
  readonly id: string
  readonly action: ReviewAction
  readonly value?: string | undefined
}

export function useResolveReview() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action, value }: ResolveInput) =>
      unwrap(
        api.POST("/api/v1/review/{item_id}", {
          params: { path: { item_id: id } },
          body: value === undefined ? { action } : { action, value },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: standKeys.review }),
  })
}
