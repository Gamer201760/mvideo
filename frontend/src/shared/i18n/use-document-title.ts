import { useEffect } from "react"
import { useLocale } from "./use-locale"

export function useDocumentTitle(page: string | null): void {
  const { setPageTitle } = useLocale()
  useEffect(() => {
    setPageTitle(page)
    return () => setPageTitle(null)
  }, [page, setPageTitle])
}
