import { useEffect, useRef } from "react"
import {
  type AttributeReviewSlots,
  type CardReviewState,
  type ExtractedValue,
  type ResolveInput,
  useResolveReview,
} from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { Button, StatusBadge } from "@/shared/ui"
import styles from "./inline-review.module.css"
import { InlineValue } from "./inline-value"

function hasFullScore(value: ExtractedValue): boolean {
  const score = value.risk?.score ?? value.confidence
  return score != null && Math.round(score * 100) === 100
}

export function useInlineReview(
  card: CardReviewState | undefined,
  disabled: boolean,
  manualMode = false,
): AttributeReviewSlots {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const resolve = useResolveReview()
  const saving = useRef(false)
  const focused = useRef<HTMLElement | null>(null)
  useEffect(() => {
    const trackFocus = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && event.target !== document.body)
        focused.current = event.target
    }
    document.addEventListener("focusin", trackFocus)
    return () => document.removeEventListener("focusin", trackFocus)
  }, [])
  const inputFor = (value: ExtractedValue): ResolveInput | null => {
    const item = card?.items.find(
      (item) => item.attribute === value.attribute && item.evidence === value.evidence,
    )
    const id = item?.id ?? value.review_id
    if (id == null) return null
    return item?.status !== undefined &&
      item.status !== "pending" &&
      item.status !== "auto_accepted"
      ? { id, action: "correct", override: true, expectedValue: item.resolved_value ?? value.value }
      : { id, action: "correct" }
  }
  const act = (input: ResolveInput, onSaved?: () => void) => {
    if (disabled || saving.current) return
    saving.current = true
    resolve.mutate(input, {
      onSuccess: () => {
        onSaved?.()
        if (document.activeElement === document.body && focused.current?.isConnected)
          focused.current.focus({ preventScroll: true })
      },
      onSettled: () => {
        saving.current = false
      },
    })
  }
  const errorFor = (id: string | undefined, action: ResolveInput["action"]) =>
    resolve.isError && resolve.variables.id === id && resolve.variables.action === action
      ? errorCopy(resolve.error).description
      : undefined

  return {
    value: (value) => {
      const input = inputFor(value)
      if (input === null) return value.value
      return (
        <InlineValue
          key={input.id}
          attribute={value.attribute}
          value={value.value}
          input={input}
          disabled={disabled}
          pending={resolve.isPending}
          error={errorFor(input.id, "correct")}
          onSave={act}
        />
      )
    },
    actions: (value) => {
      const input = inputFor(value)
      if (value.status === "accepted")
        return (
          <StatusBadge
            tone="neutral"
            icon="check"
            label={t(
              value.acceptance === "automatic"
                ? "stand:result.status.automatic"
                : "stand:result.status.accepted",
            )}
          />
        )
      if (!manualMode && hasFullScore(value)) return null
      if (input === null || input.override) return null
      return (
        <div className={styles.action}>
          <Button
            size="compact"
            variant="ghost"
            icon="check"
            aria-label={t("stand:review.acceptInline", { attribute: value.attribute })}
            disabled={disabled || resolve.isPending}
            pending={resolve.isPending && resolve.variables.id === input.id}
            onClick={() =>
              act({ id: input.id, action: "accept" }, () =>
                document.querySelector<HTMLElement>("[data-review-summary]")?.focus(),
              )
            }
          >
            {t("stand:review.confirm")}
          </Button>
          {errorFor(input.id, "accept") === undefined ? null : (
            <span className={styles.error} role="alert">
              {errorFor(input.id, "accept")}
            </span>
          )}
        </div>
      )
    },
  }
}
