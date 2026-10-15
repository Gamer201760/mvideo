import { clsx } from "clsx"
import { useReducedMotion } from "../../../motion"
import { Icon } from "../../primitives/icon/icon"
import styles from "./spinner.module.css"

export interface SpinnerProps {
  readonly label: string
  readonly className?: string | undefined
}

export function Spinner({ label, className }: SpinnerProps) {
  const reduced = useReducedMotion()
  return (
    <span className={clsx(styles.spinner, className)} role="status">
      <Icon name="loader" size="sm" className={styles.glyph} />
      <span className={reduced ? styles.label : "visually-hidden"}>{label}</span>
    </span>
  )
}
