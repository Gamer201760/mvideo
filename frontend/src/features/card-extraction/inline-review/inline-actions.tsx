import type { ExtractedValue, ResolveInput } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, StatusBadge } from "@/shared/ui"
import styles from "./inline-review.module.css"

interface InlineActionsProps {
  readonly value: ExtractedValue
  readonly input: ResolveInput | null
  readonly manualMode: boolean
  readonly disabled: boolean
  readonly pendingAction: ResolveInput["action"] | undefined
  readonly error: string | undefined
  readonly onAct: (input: ResolveInput) => void
}

function hasFullScore(value: ExtractedValue): boolean {
  const score = value.risk?.score ?? value.confidence
  return score != null && Math.round(score * 100) === 100
}

export function InlineActions({
  value,
  input,
  manualMode,
  disabled,
  pendingAction,
  error,
  onAct,
}: InlineActionsProps) {
  const { t } = useTranslation()
  const accepted = value.status === "accepted"
  const badge = accepted ? (
    <StatusBadge
      tone="neutral"
      icon="check"
      label={t(
        value.acceptance === "automatic"
          ? "stand:result.status.automatic"
          : "stand:result.status.accepted",
      )}
    />
  ) : null
  if (input === null) return badge
  const confirm = !accepted && !input.override && (manualMode || !hasFullScore(value))
  return (
    <div className={styles.action}>
      {badge}
      {confirm ? (
        <Button
          size="compact"
          variant="ghost"
          icon="check"
          aria-label={t("stand:review.acceptInline", { attribute: value.attribute })}
          disabled={disabled}
          pending={pendingAction === "accept"}
          onClick={() => onAct({ id: input.id, action: "accept" })}
        >
          {t("stand:review.confirm")}
        </Button>
      ) : null}
      <Button
        size="compact"
        variant="ghost"
        icon="reject"
        iconOnly
        aria-label={t("stand:review.rejectInline", { attribute: value.attribute })}
        title={t("stand:review.rejectInline", { attribute: value.attribute })}
        disabled={disabled}
        pending={pendingAction === "reject"}
        onClick={() => onAct({ ...input, action: "reject" })}
      >
        <span className="visually-hidden">{t("stand:review.reject")}</span>
      </Button>
      {error === undefined ? null : (
        <span className={styles.error} role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
