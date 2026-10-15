import { clsx } from "clsx"
import type { ReactNode } from "react"
import { Icon, type IconName } from "../../primitives/icon/icon"
import styles from "./empty-state.module.css"

export interface EmptyStateProps {
  readonly title: string
  readonly description?: string | undefined
  readonly icon: IconName
  readonly action?: ReactNode
  readonly className?: string | undefined
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div className={clsx(styles.empty, className)} data-motion="fade">
      <Icon name={icon} size="xl" className={styles.icon} />
      <p className={styles.title}>{title}</p>
      {description === undefined ? null : <p className={styles.description}>{description}</p>}
      {action === undefined ? null : <div className={styles.action}>{action}</div>}
    </div>
  )
}
