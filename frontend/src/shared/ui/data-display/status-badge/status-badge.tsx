import { clsx } from "clsx"
import { Icon, type IconName } from "../../primitives/icon/icon"
import styles from "./status-badge.module.css"

export type StatusTone = "success" | "warning" | "danger" | "neutral"

const TONE_CLASS: Readonly<Record<StatusTone, string | undefined>> = {
  success: styles.success,
  warning: styles.warning,
  danger: styles.danger,
  neutral: styles.neutral,
}

export interface StatusBadgeProps {
  readonly tone: StatusTone
  readonly icon: IconName
  readonly label: string
  readonly className?: string | undefined
}

export function StatusBadge({ tone, icon, label, className }: StatusBadgeProps) {
  return (
    <span className={clsx(styles.badge, TONE_CLASS[tone], className)}>
      <Icon name={icon} size="sm" />
      <span>{label}</span>
    </span>
  )
}
