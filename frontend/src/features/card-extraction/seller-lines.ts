import type { SellerParam } from "@/entities/stand"

const SEPARATOR = ":"

export type SellerLineReason = "missing_separator" | "missing_name" | "missing_value"

export interface SellerLineIssue {
  readonly line: number
  readonly text: string
  readonly reason: SellerLineReason
}

export interface SellerLines {
  readonly params: SellerParam[]
  readonly issues: SellerLineIssue[]
}

function invalidReason(at: number, name: string, value: string): SellerLineReason | null {
  if (at < 0) return "missing_separator"
  if (name === "") return "missing_name"
  if (value === "") return "missing_value"
  return null
}

export function parseSellerLines(text: string): SellerLines {
  const params: SellerParam[] = []
  const issues: SellerLineIssue[] = []
  for (const [index, raw] of text.split(/\r\n|\n|\r/).entries()) {
    if (raw.trim() === "") continue
    const at = raw.indexOf(SEPARATOR)
    const name = at < 0 ? "" : raw.slice(0, at).trim()
    const value = at < 0 ? "" : raw.slice(at + 1).trim()
    const reason = invalidReason(at, name, value)
    if (reason === null) params.push({ name, value, unit: null })
    else issues.push({ line: index + 1, text: raw, reason })
  }
  return { params, issues }
}

export function formatSellerLines(params: readonly SellerParam[]): string {
  return params
    .map((p) => `${p.name}${SEPARATOR} ${p.unit ? `${p.value} ${p.unit}` : p.value}`)
    .join("\n")
}
