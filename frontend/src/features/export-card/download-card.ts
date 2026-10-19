import type { CardExport } from "@/entities/stand"

export function downloadCard(card: CardExport) {
  const blob = new Blob([`${JSON.stringify(card, null, 2)}\n`], {
    type: "application/json;charset=utf-8",
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  const title = card.input.title.normalize("NFC").replace(/[^\p{L}\p{N}-]+/gu, "_")
  link.href = url
  link.download = `card-${title.slice(0, 80)}.json`
  document.body.append(link)
  try {
    link.click()
  } finally {
    link.remove()
    URL.revokeObjectURL(url)
  }
}
