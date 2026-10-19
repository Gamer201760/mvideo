import {
  type CardReviewState,
  type ExtractInput,
  type ExtractResult,
  latestDecisions,
  useResolveReview,
} from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { Button, Card, StatusBadge } from "@/shared/ui"
import { MissingAttribute } from "../missing-attribute/missing-attribute"
import styles from "./card-completion.module.css"

interface CardDecisionsProps {
  readonly input: ExtractInput
  readonly result: ExtractResult
  readonly reviews: CardReviewState | undefined
  readonly disabled: boolean
}

interface CardCompletionProps extends Omit<CardDecisionsProps, "input" | "result"> {
  readonly input: ExtractInput | undefined
  readonly result: ExtractResult | undefined
}

export function CardCompletion({ input, result, ...props }: CardCompletionProps) {
  if (input === undefined || result === undefined) return null
  return <CardDecisions input={input} result={result} {...props} />
}

function CardDecisions({ input, result, reviews, disabled }: CardDecisionsProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const restore = useResolveReview()
  const decisions = latestDecisions(reviews?.items ?? [])
  const rejected = [...decisions.values()].filter((item) => item.status === "rejected")
  const count = [...result.values, ...(result.extra_values ?? [])].filter(
    (value) => value.status === "review",
  ).length
  const request = {
    ...input,
    category_id: result.category?.category_id ?? input.category_id ?? null,
  }
  return (
    <Card title={t("stand:review.title")} motionIndex={3}>
      <div className={styles.content}>
        <p className={styles.summary} role="status" tabIndex={-1} data-review-summary="">
          {t("stand:review.currentCount", { count })}
        </p>
        {rejected.length === 0 ? null : (
          <section aria-label={t("stand:review.rejectedTitle")} className={styles.rejected}>
            <StatusBadge tone="neutral" icon="reject" label={t("stand:review.rejectedTitle")} />
            <ul className={styles.list}>
              {rejected.map((item) => (
                <li key={item.id}>
                  <span lang="ru">
                    {item.attribute}: {item.value}
                  </span>
                  <Button
                    variant="ghost"
                    size="compact"
                    icon="retry"
                    disabled={disabled || restore.isPending}
                    pending={restore.isPending && restore.variables.id === item.id}
                    onClick={() =>
                      restore.mutate(
                        { id: item.id, action: "correct", value: item.value, override: true },
                        {
                          onSuccess: () =>
                            document.querySelector<HTMLElement>("[data-review-summary]")?.focus(),
                        },
                      )
                    }
                  >
                    {t("stand:review.restoreInline", { attribute: item.attribute })}
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}
        {restore.isError ? <p role="alert">{errorCopy(restore.error).description}</p> : null}
        {request.category_id === null || result.missing.length === 0 ? null : (
          <ul className={styles.fields} aria-label={t("stand:result.missingTitle")}>
            {result.missing.map((attribute) => (
              <li key={attribute}>
                <MissingAttribute
                  attribute={attribute}
                  input={request}
                  text={result.text}
                  disabled={disabled}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}
