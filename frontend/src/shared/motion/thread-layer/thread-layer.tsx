import { type RefObject, useEffect, useLayoutEffect, useState } from "react"
import { readPixels } from "../css-tokens"
import { measureThread, type Thread } from "./thread-geometry"
import styles from "./thread-layer.module.css"

export interface ThreadLayerProps {
  readonly root: RefObject<HTMLElement | null>
  readonly activeKey: string | null
  readonly instant?: boolean
}

export function ThreadLayer({ root, activeKey, instant = false }: ThreadLayerProps) {
  const [layout, setLayout] = useState(0)
  const [thread, setThread] = useState<Thread | null>(null)

  useLayoutEffect(() => {
    const element = root.current
    if (element === null || activeKey === null || layout < 0) {
      setThread(null)
      return
    }
    setThread(
      measureThread(element, activeKey, {
        lead: readPixels("--thread-lead"),
        rowAnchor: readPixels("--target-min") / 2,
      }),
    )
  }, [root, activeKey, layout])

  useEffect(() => {
    const element = root.current
    if (element === null || typeof ResizeObserver === "undefined") return
    let frame = 0
    const remeasure = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => setLayout((value) => value + 1))
    }
    const observer = new ResizeObserver(remeasure)
    observer.observe(element)
    for (const lane of element.querySelectorAll("[data-thread-lane]")) observer.observe(lane)
    window.addEventListener("scroll", remeasure, { capture: true, passive: true })
    return () => {
      observer.disconnect()
      window.removeEventListener("scroll", remeasure, { capture: true })
      window.cancelAnimationFrame(frame)
    }
  }, [root])

  if (thread === null) return null
  return (
    <svg className={styles.layer} data-instant={instant} aria-hidden="true" focusable="false">
      <path key={thread.key} className={styles.thread} d={thread.path} pathLength={1} />
      <path key={`${thread.key}-arrow`} className={styles.arrow} d={thread.arrow} />
    </svg>
  )
}
