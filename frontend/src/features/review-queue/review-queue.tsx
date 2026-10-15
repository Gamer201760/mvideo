import { useResolveReview, useReviewQueue } from "@/entities/stand"
import { useErrorText, useTranslation } from "@/shared/i18n"
import { Swap, useLoadingIndicator } from "@/shared/motion"
import { Card, EmptyState, ErrorState, Skeleton } from "@/shared/ui"
import styles from "./review-queue.module.css"
import { ReviewRow } from "./review-row/review-row"

export interface ReviewQueueProps {
  readonly onResolved: () => void
}

type View = "loading" | "error" | "empty" | "data"

function viewOf(isError: boolean, loaded: boolean, count: number): View {
  if (isError) return "error"
  if (!loaded) return "loading"
  return count === 0 ? "empty" : "data"
}

export function ReviewQueue({ onResolved }: ReviewQueueProps) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const query = useReviewQueue()
  const resolve = useResolveReview()
  const items = query.data?.items ?? []
  const indicator = useLoadingIndicator({
    pending: query.isFetching,
    hasData: query.data !== undefined,
  })
  const view = viewOf(query.isError, query.data !== undefined, items.length)
  const act = (id: string, action: "accept" | "correct", value?: string) =>
    resolve.mutate({ id, action, value }, { onSuccess: onResolved })

  return (
    <Card
      title={t("stand:review.title")}
      description={t("stand:review.description")}
      eyebrow={view === "data" ? t("stand:review.count", { count: items.length }) : undefined}
      motionIndex={2}
      aria-busy={view === "loading" || undefined}
    >
      {resolve.isError ? (
        <ErrorState title={errorText(resolve.error)} onRetry={() => void query.refetch()} />
      ) : null}
      <Swap swapKey={view} as="div">
        {view === "loading" ? (
          <div role="status" aria-label={t("stand:review.loading")}>
            {indicator === "skeleton" ? <Skeleton lines={3} /> : null}
          </div>
        ) : null}
        {view === "error" ? (
          <ErrorState
            title={errorText(query.error)}
            onRetry={() => void query.refetch()}
            retryPending={query.isFetching}
          />
        ) : null}
        {view === "empty" ? (
          <EmptyState
            icon="review"
            title={t("stand:review.empty.title")}
            description={t("stand:review.empty.description")}
          />
        ) : null}
        {view === "data" ? (
          <ul className={styles.list}>
            {items.map((item) => (
              <ReviewRow
                key={item.id}
                item={item}
                pending={resolve.isPending && resolve.variables?.id === item.id}
                onAccept={() => act(item.id, "accept")}
                onCorrect={(value) => act(item.id, "correct", value)}
              />
            ))}
          </ul>
        ) : null}
      </Swap>
    </Card>
  )
}
