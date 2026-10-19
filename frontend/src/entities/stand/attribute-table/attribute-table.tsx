import { type ReactNode, useId, useState } from "react"
import { type MessageKey, useTranslation } from "@/shared/i18n"
import { Button, StatusBadge } from "@/shared/ui"
import type { ExtractedValue } from "../stand.queries"
import { AttributeAssessment, AttributeReasons } from "./attribute-assessment"
import styles from "./attribute-table.module.css"

const REVIEW_ORDER = { review: 0, unverified: 1, accepted: 2 } as const

export const SOURCE_KEY: Readonly<Record<string, MessageKey>> = {
  key_value: "stand:source.key_value",
  seller: "stand:source.seller",
  dictionary: "stand:source.dictionary",
  number: "stand:source.number",
  title_model: "stand:source.title_model",
  review: "stand:source.review",
  hybrid: "stand:source.hybrid",
  catalog_twin: "stand:source.catalog_twin",
}

export function sourceKey(source: string): MessageKey {
  return SOURCE_KEY[source] ?? "stand:source.other"
}

export interface AttributeTableProps {
  readonly values: readonly ExtractedValue[]
  readonly activeAttribute?: string | null
  readonly onFocusAttribute?: ((attribute: string | null) => void) | undefined
  readonly onOpenEvidence?: ((attribute: string, instant: boolean) => void) | undefined
  readonly evidencePanelId?: string | undefined
  readonly reviewSlots?: AttributeReviewSlots | undefined
}

export interface AttributeReviewSlots {
  readonly value: (value: ExtractedValue) => ReactNode
  readonly actions: (value: ExtractedValue) => ReactNode
}

function StatusCell({ value }: { readonly value: ExtractedValue }) {
  const { t } = useTranslation()
  if (value.status === "unverified") return null
  if (value.status === "review") {
    return <StatusBadge tone="warning" icon="review" label={t("stand:result.status.review")} />
  }
  return (
    <StatusBadge
      tone="success"
      icon="success"
      label={t(
        value.acceptance === "automatic"
          ? "stand:result.status.automatic"
          : "stand:result.status.accepted",
      )}
    />
  )
}

export function AttributeTable({
  values,
  activeAttribute = null,
  onFocusAttribute,
  onOpenEvidence,
  evidencePanelId,
  reviewSlots,
}: AttributeTableProps) {
  const { t } = useTranslation()
  const detailsId = useId()
  const [expanded, setExpanded] = useState<string | null>(null)
  const hasRisk = values.some((value) => value.risk != null)
  const ordered = values.toSorted(
    (left, right) => REVIEW_ORDER[left.status] - REVIEW_ORDER[right.status],
  )
  return (
    <table className={styles.table}>
      <thead>
        <tr className={styles.headRow}>
          <th scope="col" className={styles.head}>
            {t("stand:result.columns.attribute")}
          </th>
          <th scope="col" className={styles.head}>
            {t("stand:result.columns.value")}
          </th>
          <th scope="col" className={styles.head}>
            {hasRisk ? t("stand:risk.title") : t("stand:result.columns.confidence")}
          </th>
          <th scope="col" className={styles.head}>
            {t("stand:result.columns.quote")}
          </th>
        </tr>
      </thead>
      {ordered.map((value, index) => (
        <tbody
          key={value.attribute}
          className={styles.group}
          data-active={value.attribute === activeAttribute}
        >
          <tr
            className={styles.row}
            data-status={value.status}
            data-review-id={value.review_id ?? undefined}
            data-active={value.attribute === activeAttribute}
            data-thread-source={value.attribute}
            onPointerEnter={() => onFocusAttribute?.(value.attribute)}
            onPointerLeave={() => onFocusAttribute?.(null)}
          >
            <th scope="row" className={styles.attribute}>
              {value.attribute}
            </th>
            <td className={styles.value} lang="ru">
              {reviewSlots === undefined ? value.value : reviewSlots.value(value)}
            </td>
            <td className={styles.confidence}>
              <div className={styles.toolbar}>
                <AttributeAssessment value={value} compact />
                {!value.risk?.reasons.length ? null : (
                  <Button
                    variant="ghost"
                    icon="unknown"
                    iconOnly
                    className={styles.reasonToggle}
                    title={t("stand:risk.explain", { attribute: value.attribute })}
                    aria-expanded={expanded === value.attribute}
                    aria-controls={
                      expanded === value.attribute ? `${detailsId}-${index}` : undefined
                    }
                    onClick={() =>
                      setExpanded(expanded === value.attribute ? null : value.attribute)
                    }
                  >
                    <span className="visually-hidden">
                      {t("stand:risk.explain", { attribute: value.attribute })}
                    </span>
                  </Button>
                )}
                {reviewSlots === undefined ? (
                  <StatusCell value={value} />
                ) : (
                  reviewSlots.actions(value)
                )}
              </div>
            </td>
            <td className={styles.evidence}>
              {onOpenEvidence === undefined ? (
                <q className={styles.quote} lang="ru">
                  {value.evidence}
                </q>
              ) : (
                <Button
                  variant="ghost"
                  icon="quote"
                  className={styles.quoteButton}
                  aria-label={t("stand:evidence.openAttribute", { attribute: value.attribute })}
                  aria-controls={evidencePanelId}
                  aria-expanded={activeAttribute === value.attribute}
                  onClick={(event) => onOpenEvidence(value.attribute, event.detail === 0)}
                >
                  <q className={styles.quote} lang="ru">
                    {value.evidence}
                  </q>
                </Button>
              )}
            </td>
          </tr>
          {expanded !== value.attribute ? null : (
            <tr className={styles.detailRow}>
              <td colSpan={4}>
                <div id={`${detailsId}-${index}`} className={styles.details}>
                  <AttributeReasons value={value} />
                </div>
              </td>
            </tr>
          )}
        </tbody>
      ))}
    </table>
  )
}
