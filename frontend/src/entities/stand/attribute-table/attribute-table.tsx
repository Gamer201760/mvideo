import { type MessageKey, useFormatters, useTranslation } from "@/shared/i18n"
import { StatusBadge } from "@/shared/ui"
import type { ExtractedValue } from "../stand.queries"
import styles from "./attribute-table.module.css"

export const SOURCE_KEY: Readonly<Record<string, MessageKey>> = {
  key_value: "stand:source.key_value",
  seller: "stand:source.seller",
  dictionary: "stand:source.dictionary",
  number: "stand:source.number",
  title_model: "stand:source.title_model",
  review: "stand:source.review",
  catalog_twin: "stand:source.catalog_twin",
  neighbor: "stand:source.neighbor",
}

export function sourceKey(source: string): MessageKey {
  return SOURCE_KEY[source] ?? "stand:source.other"
}

export interface AttributeTableProps {
  readonly values: readonly ExtractedValue[]
  readonly onFocusAttribute: (attribute: string | null) => void
}

export function AttributeTable({ values, onFocusAttribute }: AttributeTableProps) {
  const { t } = useTranslation()
  const { percent } = useFormatters()
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
            {t("stand:result.columns.confidence")}
          </th>
          <th scope="col" className={styles.head}>
            {t("stand:result.columns.source")}
          </th>
          <th scope="col" className={styles.head}>
            {t("stand:result.columns.quote")}
          </th>
        </tr>
      </thead>
      <tbody>
        {values.map((value) => (
          <tr
            key={value.attribute}
            className={styles.row}
            data-status={value.status}
            onPointerEnter={() => onFocusAttribute(value.attribute)}
            onPointerLeave={() => onFocusAttribute(null)}
          >
            <th scope="row" className={styles.attribute}>
              {value.attribute}
            </th>
            <td className={styles.value} lang="ru">
              {value.value}
            </td>
            <td className={styles.confidence}>
              <span className={styles.number}>{percent(value.confidence)}</span>
              {value.status === "review" ? (
                <StatusBadge tone="warning" icon="review" label={t("stand:result.status.review")} />
              ) : (
                <StatusBadge
                  tone="success"
                  icon="success"
                  label={t("stand:result.status.accepted")}
                />
              )}
            </td>
            <td className={styles.source}>{t(sourceKey(value.source))}</td>
            <td className={styles.quote} lang="ru">
              {value.evidence}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
