import { type ReactNode, useState } from "react"
import {
  RUN_PAGE_SIZE,
  type RunDetail,
  type RunSummary,
  useOpenRun,
  useRuns,
} from "@/entities/stand"
import { type MessageKey, useErrorCopy, useFormatters, useTranslation } from "@/shared/i18n"
import { Button, Card, EmptyState, ErrorState, Skeleton, StatusBadge } from "@/shared/ui"
import styles from "./run-history.module.css"

export interface RunHistoryProps {
  readonly onOpen: (run: RunDetail) => void
  readonly exportSlot: (run: RunSummary) => ReactNode
}

const STATUS = {
  running: "stand:history.status.running",
  completed: "stand:history.status.completed",
  failed: "stand:history.status.failed",
  interrupted: "stand:history.status.interrupted",
} as const satisfies Record<RunSummary["status"], MessageKey>

export function RunHistory({ onOpen, exportSlot }: RunHistoryProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const { dateTime } = useFormatters()
  const [offset, setOffset] = useState(0)
  const query = useRuns(offset)
  const open = useOpenRun()
  const content =
    query.data === undefined ? null : (
      <>
        <ul className={styles.list}>
          {query.data.items.map((run) => (
            <li key={run.id} id={`run-${run.id}`} className={styles.row}>
              <div className={styles.subject}>
                <p className={styles.title} lang="ru">
                  {run.title}
                </p>
                <p className={styles.meta}>{dateTime(run.started_at)}</p>
              </div>
              <StatusBadge
                icon={run.status === "completed" ? "check" : "status"}
                tone={run.status === "failed" ? "danger" : "neutral"}
                label={t(STATUS[run.status])}
              />
              <Button
                size="compact"
                icon="card"
                variant="secondary"
                disabled={run.status === "running" || open.isPending}
                pending={open.isPending && open.variables === run.id}
                onClick={() => open.mutate(run.id, { onSuccess: onOpen })}
              >
                {t("stand:history.open")}
              </Button>
              {run.status === "completed" ? exportSlot(run) : null}
            </li>
          ))}
        </ul>
        {query.data.total > RUN_PAGE_SIZE ? (
          <div className={styles.pages}>
            <Button
              variant="ghost"
              icon="chevron-right"
              disabled={offset === 0 || query.isFetching}
              onClick={() => setOffset(offset - RUN_PAGE_SIZE)}
            >
              {t("stand:review.previous")}
            </Button>
            <Button
              variant="ghost"
              icon="chevron-right"
              disabled={offset + query.data.items.length >= query.data.total || query.isFetching}
              onClick={() => setOffset(offset + RUN_PAGE_SIZE)}
            >
              {t("stand:review.next")}
            </Button>
          </div>
        ) : null}
      </>
    )
  return (
    <Card
      title={t("stand:history.title")}
      description={t("stand:history.description")}
      actions={
        <Button
          variant="ghost"
          icon="refresh"
          pending={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {t("stand:history.refresh")}
        </Button>
      }
    >
      {open.isError ? (
        <ErrorState
          {...errorCopy(open.error)}
          onRetry={() => {
            if (open.variables !== undefined) open.mutate(open.variables, { onSuccess: onOpen })
          }}
        />
      ) : null}
      {query.isError ? (
        <ErrorState {...errorCopy(query.error)} onRetry={() => void query.refetch()} />
      ) : query.data === undefined ? (
        <Skeleton lines={3} />
      ) : query.data.items.length === 0 ? (
        <EmptyState
          icon="card"
          title={t("stand:history.empty")}
          description={t("stand:history.emptyDescription")}
        />
      ) : (
        content
      )}
    </Card>
  )
}
