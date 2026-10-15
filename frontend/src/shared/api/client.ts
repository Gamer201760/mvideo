import createClient from "openapi-fetch"
import type { paths } from "./schema.gen"

export const SERVER_UNAVAILABLE = "server_unavailable"
export const NETWORK_UNAVAILABLE = "network_unavailable"
export const UNEXPECTED = "unexpected"

export type ApiErrorKind =
  | "network"
  | "auth"
  | "forbidden"
  | "notFound"
  | "conflict"
  | "validation"
  | "server"
  | "unknown"

const KIND_BY_STATUS: Readonly<Record<number, ApiErrorKind>> = {
  0: "network",
  400: "validation",
  401: "auth",
  403: "forbidden",
  404: "notFound",
  409: "conflict",
  422: "validation",
}

export function kindOf(status: number): ApiErrorKind {
  return KIND_BY_STATUS[status] ?? (status >= 500 ? "server" : "unknown")
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly kind: ApiErrorKind
  readonly detail: unknown

  constructor(status: number, code: string, detail: unknown = null) {
    super(code)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.kind = kindOf(status)
    this.detail = detail
  }
}

function unavailable(): Response {
  return new Response(JSON.stringify({ code: SERVER_UNAVAILABLE }), {
    status: 503,
    headers: { "Content-Type": "application/json" },
  })
}

export const api = createClient<paths>({ credentials: "same-origin" })

api.use({
  onResponse({ response }) {
    const isJson = response.headers.get("Content-Type")?.includes("application/json") ?? false
    return response.status >= 500 && !isJson ? unavailable() : undefined
  },
})

export function codeOf(body: unknown): string {
  if (body !== null && typeof body === "object" && "code" in body) {
    const { code } = body
    if (typeof code === "string" && code !== "") return code
  }
  return UNEXPECTED
}

interface FetchResult<Data> {
  readonly data?: Data
  readonly error?: unknown
  readonly response: Response
}

export async function unwrap<Data>(request: Promise<FetchResult<Data>>): Promise<Data> {
  let result: FetchResult<Data>
  try {
    result = await request
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error
    throw new ApiError(0, NETWORK_UNAVAILABLE, error)
  }
  if (result.response.ok) return result.data as Data
  throw new ApiError(result.response.status, codeOf(result.error), result.error)
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}
