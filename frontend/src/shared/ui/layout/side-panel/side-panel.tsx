import { type ReactNode, useEffect, useId, useRef, useSyncExternalStore } from "react"
import { usePresence } from "../../../motion"
import { Button } from "../../primitives/button/button"
import styles from "./side-panel.module.css"

const WIDE_SCREEN = "(min-width: 64rem)"

function isWide(): boolean {
  return window.matchMedia(WIDE_SCREEN).matches
}

function subscribe(listener: () => void) {
  const query = window.matchMedia(WIDE_SCREEN)
  query.addEventListener("change", listener)
  return () => query.removeEventListener("change", listener)
}

export interface SidePanelProps {
  readonly id: string
  readonly open: boolean
  readonly title: string
  readonly closeLabel: string
  readonly onClose: (instant?: boolean) => void
  readonly children: ReactNode
  readonly instant?: boolean
}

export function SidePanel({
  id,
  open,
  title,
  closeLabel,
  onClose,
  children,
  instant = false,
}: SidePanelProps) {
  const dialog = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const wide = useSyncExternalStore(subscribe, isWide, () => false)
  const presence = usePresence(open, "--dur-drawer-exit", instant)

  useEffect(() => {
    if (wide || !open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = previous
    }
  }, [wide, open])

  useEffect(() => {
    const element = dialog.current
    if (element === null) return
    if (!presence.mounted) {
      if (element.open) {
        element.close()
        opener.current?.focus({ preventScroll: true })
        opener.current = null
      }
      return
    }
    if (opener.current === null && document.activeElement instanceof HTMLElement) {
      opener.current = document.activeElement
    }
    if (element.open) element.close()
    if (wide) element.show()
    else element.showModal()
    heading.current?.focus({ preventScroll: true })
  }, [presence.mounted, wide])

  useEffect(() => {
    if (!wide || !open) return
    const rememberFocus = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && !dialog.current?.contains(event.target)) {
        opener.current = event.target
      }
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return
      event.preventDefault()
      onClose(true)
    }
    document.addEventListener("keydown", handleEscape)
    document.addEventListener("focusin", rememberFocus)
    return () => {
      document.removeEventListener("keydown", handleEscape)
      document.removeEventListener("focusin", rememberFocus)
    }
  }, [wide, open, onClose])

  return (
    <dialog
      id={id}
      ref={dialog}
      className={styles.panel}
      aria-labelledby={titleId}
      aria-modal={wide ? undefined : true}
      data-state={presence.state}
      data-instant={instant}
      data-motion="fade"
      data-thread-lane=""
      onAnimationEnd={presence.onAnimationEnd}
      onCancel={(event) => {
        event.preventDefault()
        onClose(true)
      }}
    >
      <header className={styles.header}>
        <h2 id={titleId} ref={heading} tabIndex={-1} className={styles.title}>
          {title}
        </h2>
        <Button
          variant="ghost"
          icon="chevron-right"
          onClick={(event) => onClose(event.detail === 0)}
        >
          {closeLabel}
        </Button>
      </header>
      <div className={styles.content}>{children}</div>
    </dialog>
  )
}
