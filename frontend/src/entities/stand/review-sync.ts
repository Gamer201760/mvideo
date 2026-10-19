import { useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

const REVIEW_EVENT = "stand-review-updated"

export function publishReviewChange() {
  try {
    localStorage.setItem(REVIEW_EVENT, crypto.randomUUID())
  } catch {
    return
  }
}

export function useReviewSync(queryKey: readonly string[]) {
  const client = useQueryClient()
  useEffect(() => {
    const refresh = () => void client.invalidateQueries({ queryKey })
    const receive = (event: StorageEvent) => {
      if (event.key === REVIEW_EVENT) refresh()
    }
    window.addEventListener("focus", refresh)
    window.addEventListener("storage", receive)
    return () => {
      window.removeEventListener("focus", refresh)
      window.removeEventListener("storage", receive)
    }
  }, [client, queryKey])
}
