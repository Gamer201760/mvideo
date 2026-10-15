import type { TextResult } from "@/entities/stand"
import { useFormatters, useTranslation } from "@/shared/i18n"
import styles from "./text-summary.module.css"

export interface TextSummaryProps {
  readonly result: TextResult
}

export function TextSummary({ result }: TextSummaryProps) {
  const { t } = useTranslation()
  const { percent } = useFormatters()
  const others = result.candidates.filter((c) => c.category_id !== result.category_id)
  const searchKey = result.search === "embeddings" ? "embeddings" : "tfidf"
  return (
    <dl className={styles.summary}>
      <div className={styles.row}>
        <dt className={styles.label}>{t("stand:text.category")}</dt>
        <dd className={styles.value} lang="ru">
          {result.category_id === null ? (
            <span className={styles.muted}>{t("stand:text.categoryUnknown")}</span>
          ) : (
            <span className={styles.meta}>
              <span className={styles.strong}>{result.category_name ?? result.category_id}</span>
              <span className={styles.muted}>
                {t("stand:text.categoryConfidence", {
                  value: percent(result.category_confidence),
                })}
              </span>
              <span className={styles.muted}>{t(`stand:text.search.${searchKey}`)}</span>
            </span>
          )}
        </dd>
      </div>
      {others.length === 0 ? null : (
        <div className={styles.row}>
          <dt className={styles.label}>{t("stand:text.candidates")}</dt>
          <dd className={styles.value} lang="ru">
            {others.map((c) => `${c.name ?? c.category_id} (${percent(c.confidence)})`).join(", ")}
          </dd>
        </div>
      )}
      <div className={styles.row}>
        <dt className={styles.label}>{t("stand:text.productTitle")}</dt>
        <dd className={styles.value} lang="ru">
          {result.title === null ? (
            <span className={styles.muted}>{t("stand:text.titleNone")}</span>
          ) : (
            <>
              <span className={styles.strong}>{result.title.value}</span>{" "}
              <span className={styles.muted}>
                {t(
                  result.title.source === "llm"
                    ? "stand:text.titleSource.llm"
                    : "stand:text.titleSource.rule",
                )}
              </span>
            </>
          )}
        </dd>
      </div>
    </dl>
  )
}
