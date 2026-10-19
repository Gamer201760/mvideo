import { useCallback, useEffect, useLayoutEffect, useRef } from "react"
import { motionMs, readEasing, readPixels } from "./css-tokens"
import { useReducedMotion } from "./use-reduced-motion"

export function useReorderMotion(order: string) {
  const reduced = useReducedMotion()
  const elements = useRef(new Map<string, HTMLElement>())
  const positions = useRef(new Map<string, number>())
  const animations = useRef(new Map<string, Animation>())
  const itemRef = useCallback(
    (key: string) => (element: HTMLElement | null) => {
      if (element === null) elements.current.delete(key)
      else elements.current.set(key, element)
    },
    [],
  )

  useLayoutEffect(() => {
    const keys = new Set(order.split(","))
    const boxes = [...elements.current]
      .filter(([key]) => keys.has(key))
      .map(([key, element]) => {
        const transform = getComputedStyle(element).transform
        const offset = !transform || transform === "none" ? 0 : new DOMMatrixReadOnly(transform).m42
        const top = element.getBoundingClientRect().top + window.scrollY - offset
        const previous = positions.current.get(key)
        return { key, element, top, delta: previous === undefined ? 0 : previous + offset - top }
      })
    for (const { key, element, top, delta } of boxes) {
      animations.current.get(key)?.cancel()
      animations.current.delete(key)
      delete element.dataset.reordering
      positions.current.set(key, top)
      if (reduced || delta === 0 || typeof element.animate !== "function") continue
      element.dataset.reordering = delta > 0 ? "up" : "down"
      const shift = readPixels("--space-12") * (delta > 0 ? 1 : -1)
      const animation = element.animate(
        [
          { transform: `translateY(${delta}px)` },
          { transform: `translateY(${delta / 2}px) translateX(${shift}px)` },
          { transform: "translateY(0)" },
        ],
        { duration: motionMs("--dur-draw"), easing: readEasing("--ease-in-out") },
      )
      animations.current.set(key, animation)
      void animation.finished.then(
        () => {
          if (animations.current.get(key) === animation) delete element.dataset.reordering
        },
        () => undefined,
      )
    }
  }, [order, reduced])

  useEffect(() => {
    const running = animations.current
    const resize = () => {
      for (const animation of running.values()) animation.cancel()
      running.clear()
      for (const [key, element] of elements.current) {
        delete element.dataset.reordering
        positions.current.set(key, element.getBoundingClientRect().top + window.scrollY)
      }
    }
    window.addEventListener("resize", resize)
    return () => {
      window.removeEventListener("resize", resize)
      for (const animation of running.values()) animation.cancel()
    }
  }, [])

  return itemRef
}
