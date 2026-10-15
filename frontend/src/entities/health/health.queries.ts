import { useQuery } from "@tanstack/react-query"
import { api, unwrap } from "@/shared/api"

export const HEALTH_PATH = "/api/v1/health"

export const healthKeys = {
  all: ["health"] as const,
}

export function useHealth() {
  return useQuery({
    queryKey: healthKeys.all,
    queryFn: ({ signal }) => unwrap(api.GET(HEALTH_PATH, { signal })),
    retry: false,
  })
}
