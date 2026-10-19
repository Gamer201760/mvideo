import type { ExtractResult } from "@/entities/stand"
import { type MessageKey, useTranslation } from "@/shared/i18n"
import styles from "./rejected-fields.module.css"

const REASONS: Readonly<Record<string, MessageKey>> = {
  invalid_evidence: "stand:rejections.invalidEvidence",
  conflicting_values: "stand:rejections.conflictingValues",
  model_conflict: "stand:rejections.conflictingValues",
  object_context: "stand:rejections.otherProduct",
  field_mismatch: "stand:rejections.otherField",
  field_unconfirmed: "stand:rejections.fieldUnconfirmed",
  field_type_mismatch: "stand:rejections.fieldTypeMismatch",
  conditional_support: "stand:rejections.conditionalSupport",
  negation: "stand:rejections.negation",
  negation_unconfirmed: "stand:rejections.negation",
  unit_mismatch: "stand:rejections.unitMismatch",
  number_unconfirmed: "stand:rejections.numberUnconfirmed",
  range_mismatch: "stand:rejections.rangeMismatch",
  range_lost: "stand:rejections.rangeLost",
  value_unconfirmed: "stand:rejections.valueUnconfirmed",
}

interface RejectedFieldsProps {
  readonly rejections: ExtractResult["rejections"]
}

export function RejectedFields({ rejections = [] }: RejectedFieldsProps) {
  const { t } = useTranslation()
  if (rejections.length === 0) return null
  return (
    <section className={styles.section} aria-label={t("stand:rejections.title")}>
      <p className={styles.title}>{t("stand:rejections.title")}</p>
      <ul className={styles.list}>
        {rejections.map((rejection) => (
          <li key={`${rejection.attribute}:${rejection.reason}:${rejection.evidence}`}>
            <span lang="ru" className={styles.attribute}>
              {rejection.attribute}
            </span>
            <p className={styles.reason}>
              {t(REASONS[rejection.reason] ?? "stand:rejections.valueUnconfirmed")}
            </p>
            <blockquote lang="ru" className={styles.quote}>
              {rejection.evidence}
            </blockquote>
          </li>
        ))}
      </ul>
    </section>
  )
}
