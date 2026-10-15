import { useErrorText, useFormatters, useTranslation } from "@/shared/i18n"
import { Swap, useLoadingIndicator } from "@/shared/motion"
import { Button, Card, ErrorState, Icon, Skeleton, Spinner } from "@/shared/ui"
import { HEALTH_PATH, useHealth } from "../health.queries"
import styles from "./health-card.module.css"
import { healthView } from "./health-view"

export interface HealthCardProps {
  readonly motionIndex?: number | undefined
}

export function HealthCard({ motionIndex }: HealthCardProps) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const { time } = useFormatters()
  const query = useHealth()
  const hasData = query.data !== undefined
  const indicator = useLoadingIndicator({
    pending: query.isFetching && !query.isError,
    hasData,
  })
  const view = healthView({ isError: query.isError, hasData }, indicator)
  const refetch = () => {
    void query.refetch()
  }

  return (
    <Card
      title={t("health:title")}
      eyebrow={HEALTH_PATH}
      motionIndex={motionIndex}
      aria-busy={view === "loading" || undefined}
      actions={
        view === "ok" ? (
          <Button
            variant="ghost"
            size="compact"
            icon="refresh"
            pending={query.isFetching}
            onClick={refetch}
          >
            {t("health:recheck")}
          </Button>
        ) : undefined
      }
    >
      <Swap swapKey={view} as="div" className={styles.body}>
        {view === "loading" ? (
          <div className={styles.loading} role="status" aria-label={t("health:loading")}>
            <Skeleton lines={2} />
          </div>
        ) : null}
        {view === "error" ? (
          <ErrorState
            title={errorText(query.error)}
            onRetry={refetch}
            retryPending={query.isFetching}
          />
        ) : null}
        {view === "ok" ? (
          <div className={styles.ok} data-stale={indicator === "stale" || indicator === "spinner"}>
            <p className={styles.status}>
              <Icon name="success" size="md" className={styles.success} />
              <span>{t("health:ok")}</span>
            </p>
            <p className={styles.checked}>
              {t("health:checkedAt", { time: time(query.dataUpdatedAt) })}
            </p>
            {indicator === "spinner" ? <Spinner label={t("health:loading")} /> : null}
          </div>
        ) : null}
      </Swap>
    </Card>
  )
}
