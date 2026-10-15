import { useEffect, useRef } from "react"
import { useLocation } from "react-router"

export function useRouteFocus(): void {
  const { pathname } = useLocation()
  const previous = useRef<string | null>(null)
  useEffect(() => {
    const changed = previous.current !== null && previous.current !== pathname
    previous.current = pathname
    if (!changed) return
    const frame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#main h1")?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [pathname])
}
