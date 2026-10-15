import { QueryClient } from "@tanstack/react-query"
import { ApiError } from "./client"

const MAX_RETRIES = 2
const STALE_TIME_MS = 15_000

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status > 0 && error.status < 500) return false
  return failureCount < MAX_RETRIES
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: STALE_TIME_MS, refetchOnWindowFocus: true },
      mutations: { retry: false },
    },
  })
}
