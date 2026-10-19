import {
  type CardReviewState,
  type ExtractInput,
  type ReviewAction,
  useResolveReview,
} from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { Card, ErrorState } from "@/shared/ui"
import { ReviewItems } from "./review-items/review-items"

export interface ReviewQueueProps {
  readonly card: CardReviewState | undefined
  readonly onResolved: (card: ExtractInput) => void
}

export function ReviewQueue({ card, onResolved }: ReviewQueueProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const resolve = useResolveReview()
  const current = card?.items.filter((item) => item.status === "pending") ?? []
  const act = (id: string, action: ReviewAction, value?: string) =>
    resolve.mutate(
      { id, action, value },
      {
        onSuccess: ({ card }) => {
          if (card !== null) onResolved(card)
        },
      },
    )

  if (card === undefined || current.length === 0) return null

  return (
    <Card
      title={t("stand:review.title")}
      description={t("stand:review.description")}
      eyebrow={t("stand:review.currentCount", { count: current.length })}
      motionIndex={2}
    >
      {resolve.isError ? (
        <ErrorState
          {...errorCopy(resolve.error)}
          onRetry={() => {
            const input = resolve.variables
            if (input !== undefined) act(input.id, input.action, input.value)
          }}
          retryPending={resolve.isPending}
        />
      ) : null}
      {resolve.isSuccess && resolve.data.card === null ? (
        <p role="status">{t("stand:review.savedWithoutCard")}</p>
      ) : null}
      <ReviewItems
        items={current}
        pendingId={resolve.isPending ? resolve.variables.id : undefined}
        onAct={act}
      />
    </Card>
  )
}
