import { clsx } from "clsx"
import { type ReactNode, useId, useState } from "react"
import { useInputModality, usePresence } from "../../../motion"
import { Icon, type IconName } from "../../primitives/icon/icon"
import styles from "./disclosure.module.css"

export interface DisclosureProps {
  readonly label: string
  readonly hint?: string | undefined
  readonly icon?: IconName | undefined
  readonly defaultOpen?: boolean
  readonly open?: boolean | undefined
  readonly onOpenChange?: ((open: boolean) => void) | undefined
  readonly className?: string | undefined
  readonly children: ReactNode
}

export function Disclosure({
  label,
  hint,
  icon,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  className,
  children,
}: DisclosureProps) {
  const id = useId()
  const [expanded, setExpanded] = useState(defaultOpen)
  const open = controlledOpen ?? expanded
  const modality = useInputModality()
  const presence = usePresence(open, "--dur-exit", modality.instant)
  const panelId = `${id}-panel`
  return (
    <div className={clsx(styles.disclosure, className)}>
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={presence.mounted ? panelId : undefined}
        onKeyDown={modality.onKeyDown}
        onPointerDown={modality.onPointerDown}
        onClick={() => {
          setExpanded(!open)
          onOpenChange?.(!open)
        }}
      >
        {icon === undefined ? null : <Icon name={icon} size="sm" className={styles.icon} />}
        <span className={styles.text}>
          <span className={styles.label}>{label}</span>
          {hint === undefined ? null : <span className={styles.hint}>{hint}</span>}
        </span>
        <Icon name="chevron-down" size="sm" className={styles.chevron} />
      </button>
      {presence.mounted ? (
        <div
          id={panelId}
          className={styles.panel}
          data-state={presence.state}
          data-instant={modality.instant}
          data-motion="fade"
          onAnimationEnd={presence.onAnimationEnd}
        >
          {children}
        </div>
      ) : null}
    </div>
  )
}
