import type { SellerParam } from "@/entities/stand"

const SEPARATOR = ":"

export function parseSellerLines(text: string): SellerParam[] {
  const params: SellerParam[] = []
  for (const line of text.split("\n")) {
    const at = line.indexOf(SEPARATOR)
    if (at <= 0) continue
    const name = line.slice(0, at).trim()
    const value = line.slice(at + 1).trim()
    if (name !== "" && value !== "") params.push({ name, value, unit: null })
  }
  return params
}

export function formatSellerLines(params: readonly SellerParam[]): string {
  return params
    .map((p) => `${p.name}${SEPARATOR} ${p.unit ? `${p.value} ${p.unit}` : p.value}`)
    .join("\n")
}
