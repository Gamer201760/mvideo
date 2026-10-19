import { clsx } from "clsx"
import type { ReactNode } from "react"
import { useTranslation } from "../../../i18n"
import { Button } from "../../primitives/button/button"
import { Icon, type IconName } from "../../primitives/icon/icon"
import styles from "./error-state.module.css"

export type StateLayout = "panel" | "page"

const LAYOUT_CLASS: Readonly<Record<StateLayout, string | undefined>> = {
  panel: styles.panel,
  page: styles.page,
}

export interface ErrorStateProps {
  readonly title: string
  readonly description?: ReactNode | undefined
  readonly onRetry?: (() => void) | undefined
  readonly retryPending?: boolean | undefined
  readonly action?: ReactNode
  readonly icon?: IconName | undefined
  readonly layout?: StateLayout | undefined
  readonly titleAs?: "p" | "h1" | undefined
  readonly className?: string | undefined
}

export function ErrorState({
  title,
  description,
  onRetry,
  retryPending = false,
  action,
  icon = "alert",
  layout = "panel",
  titleAs: Title = "p",
  className,
}: ErrorStateProps) {
  const { t } = useTranslation()
  const hasActions = onRetry !== undefined || action !== undefined
  return (
    <div
      className={clsx(styles.error, LAYOUT_CLASS[layout], className)}
      role="alert"
      data-motion="fade"
    >
      <span className={styles.badge}>
        <Icon name={icon} size="lg" />
      </span>
      <div className={styles.copy}>
        <Title className={styles.title}>{title}</Title>
        {description === undefined ? null : <p className={styles.description}>{description}</p>}
      </div>
      {hasActions ? (
        <div className={styles.actions}>
          {onRetry === undefined ? null : (
            <Button
              variant="secondary"
              size={layout === "page" ? "regular" : "compact"}
              icon="retry"
              pending={retryPending}
              onClick={onRetry}
            >
              {t("common:action.retry")}
            </Button>
          )}
          {action}
        </div>
      ) : null}
    </div>
  )
}
