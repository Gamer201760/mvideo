import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ApiError, api, unwrap } from "@/shared/api"
import type { components } from "@/shared/api/schema.gen"
import { publishReviewChange, useReviewSync } from "./review-sync"
import { runKeys } from "./run.queries"

type Schemas = components["schemas"]

export type StandInfo = Schemas["StandInfoResponse"]
export type StandCategory = Schemas["CategorySchema"]
export type StandExample = Schemas["ExampleSchema"]
export type SellerParam = Schemas["SellerParamSchema"]
export type ExtractInput = Schemas["ExtractRequest"]
export type ExtractResult = Schemas["ExtractResponse"]
export type ExtractedValue = Schemas["ExtractedValueSchema"]
export type ReviewItem = Schemas["ReviewItemSchema"]
export type CardReviewState = Schemas["CardReviewResponse"]
export type ReviewAction = Schemas["ResolveRequest"]["action"]

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

export function useCategoryPreview() {
  return useMutation({
    mutationFn: (body: ExtractInput) => unwrap(api.POST("/api/v1/extract/preview", { body })),
  })
}

export function useExtract() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: ExtractInput) => unwrap(api.POST("/api/v1/extract", { body })),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: standKeys.review }),
        client.invalidateQueries({ queryKey: standKeys.info }),
        client.invalidateQueries({ queryKey: runKeys.all }),
      ]),
  })
}

export function useCardReviews(input: ExtractInput | undefined) {
  useReviewSync(standKeys.review)
  return useQuery({
    queryKey: [...standKeys.review, "card", input],
    enabled: input !== undefined,
    queryFn: ({ signal }) => {
      if (input === undefined) throw new Error("Card input is required")
      return unwrap(api.POST("/api/v1/review/card", { body: input, signal }))
    },
  })
}

export interface ResolveInput {
  readonly id: string
  readonly action: ReviewAction
  readonly value?: string | undefined
  readonly override?: boolean
  readonly expectedValue?: string
}

async function resolveReview({ id, action, value, override, expectedValue }: ResolveInput) {
  const card = await unwrap(
    api.GET("/api/v1/review/{item_id}/card", { params: { path: { item_id: id } } }),
  ).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  })
  const item = await unwrap(
    api.POST("/api/v1/review/{item_id}", {
      params: { path: { item_id: id } },
      body: {
        ...(value === undefined ? { action } : { action, value }),
        override: override ?? false,
        ...(override ? { override: true, expected_value: expectedValue ?? null } : {}),
      },
    }),
  )
  return { item, card }
}

export function useResolveReview() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: resolveReview,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        void client.invalidateQueries({ queryKey: standKeys.review })
      }
    },
    onSuccess: () => {
      publishReviewChange()
      return client.invalidateQueries({ queryKey: standKeys.review })
    },
  })
}
