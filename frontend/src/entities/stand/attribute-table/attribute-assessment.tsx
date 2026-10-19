import { type MessageKey, useTranslation } from "@/shared/i18n"
import { NoValue, ScoreMeter, StatusBadge } from "@/shared/ui"
import type { ExtractedValue } from "../stand.queries"
import styles from "./attribute-assessment.module.css"

const REASONS: Readonly<Record<string, MessageKey>> = {
  number_unconfirmed: "stand:risk.reasons.number_unconfirmed",
  negation: "stand:risk.reasons.negation",
  object_context: "stand:risk.reasons.object_context",
  range_lost: "stand:risk.reasons.range_lost",
  conflicting_values: "stand:risk.reasons.conflicting_values",
  model_scope: "stand:risk.reasons.model_scope",
  model_conflict: "stand:risk.reasons.model_conflict",
  model_inference: "stand:risk.reasons.model_inference",
  indirect_value: "stand:risk.reasons.indirect_value",
  category_ambiguity: "stand:risk.reasons.category_ambiguity",
  invalid_evidence: "stand:risk.reasons.invalid_evidence",
  exact_quote: "stand:risk.reasons.exact_quote",
  value_supported: "stand:risk.reasons.value_supported",
  number_supported: "stand:risk.reasons.number_supported",
  category_field: "stand:risk.reasons.category_field",
  field_unconfirmed: "stand:risk.reasons.field_unconfirmed",
}

const LEVEL_KEY = {
  low: "stand:risk.low",
  medium: "stand:risk.medium",
  high: "stand:risk.high",
} as const satisfies Readonly<Record<string, MessageKey>>

const SCORE_MAX = 100

export function AttributeReasons({ value }: { readonly value: ExtractedValue }) {
  const { t } = useTranslation()
  if (!value.risk?.reasons.length) return null
  return (
    <ul className={styles.reasons}>
      {value.risk.reasons.map((reason) => (
        <li key={reason}>{t(REASONS[reason] ?? "stand:risk.reasons.other")}</li>
      ))}
    </ul>
  )
}

export function AttributeAssessment({
  value,
  compact = false,
}: {
  readonly value: ExtractedValue
  readonly compact?: boolean
}) {
  const { t } = useTranslation()
  const risk = value.risk
  if (risk != null) {
    const level = t(LEVEL_KEY[risk.level])
    const points = Math.round(risk.score * SCORE_MAX)
    const flagged = risk.level !== "low"
    return (
      <div className={styles.assessment} data-level={risk.level}>
        <span className={styles.scoreLine}>
          <span className={styles.score}>
            {t("stand:risk.score", { value: points, max: SCORE_MAX })}
          </span>
          <ScoreMeter
            className={styles.meter}
            value={risk.score}
            tone={flagged ? "attention" : "settled"}
            label={t("stand:risk.meter", { level, value: points, max: SCORE_MAX })}
          />
        </span>
        {flagged ? (
          <StatusBadge
            tone={risk.level === "high" ? "danger" : "warning"}
            icon="alert"
            label={level}
          />
        ) : null}
        {compact ? null : <AttributeReasons value={value} />}
      </div>
    )
  }
  if (value.confidence === null) return <NoValue label={t("stand:result.uncalibrated")} />
  return (
    <span className={styles.scoreLine}>
      <span className={styles.score}>
        {t("stand:risk.score", { value: Math.round(value.confidence * SCORE_MAX), max: SCORE_MAX })}
      </span>
      <ScoreMeter
        className={styles.meter}
        value={value.confidence}
        tone={value.status === "review" ? "attention" : "settled"}
        label={t("stand:result.columns.confidence")}
      />
    </span>
  )
}
