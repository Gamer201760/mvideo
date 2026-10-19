import { CategoryPath, type StandCategory } from "@/entities/stand"
import { useFormatters, useTranslation } from "@/shared/i18n"
import { staggerStyle, useReorderMotion } from "@/shared/motion"
import { Card, Spinner, StatusBadge } from "@/shared/ui"
import styles from "./extraction-progress.module.css"
import { useRankingOrder } from "./use-ranking-order"

interface ExtractionProgressProps {
  readonly candidates: readonly StandCategory[] | undefined
  readonly pending: boolean
  readonly selected: number | null | undefined
}

export function ExtractionProgress({ candidates, pending, selected }: ExtractionProgressProps) {
  const { t } = useTranslation()
  const { integer } = useFormatters()
  const ordered = useRankingOrder(candidates, pending, selected)
  const itemRef = useReorderMotion(ordered.map((candidate) => candidate.category_id).join(","))
  const decided = selected !== undefined
  const label = decided
    ? selected === null
      ? t("stand:result.categoryUnknown")
      : t("stand:progress.done")
    : candidates === undefined
      ? t("stand:progress.searching")
      : t("stand:progress.extracting")
  return (
    <Card title={t("stand:progress.candidates")}>
      <div className={styles.progress}>
        <div className={styles.stage} aria-live="polite">
          {pending ? <Spinner label={label} /> : null}
          <p className={styles.label}>{label}</p>
        </div>
        <div className={styles.scan} data-active={pending && !decided} aria-hidden="true">
          <span className={styles.beam} />
        </div>
        {candidates === undefined ? null : candidates.length === 0 ? (
          <p className={styles.empty}>{t("stand:progress.empty")}</p>
        ) : (
          <ol className={styles.list} aria-label={t("stand:progress.candidates")}>
            {ordered.map((candidate, index) => {
              const chosen = candidate.category_id === selected
              return (
                <li
                  className={styles.candidate}
                  key={candidate.category_id}
                  ref={itemRef(String(candidate.category_id))}
                  data-selected={chosen}
                  data-decided={selected != null}
                  data-motion="fade"
                  style={staggerStyle(candidates.indexOf(candidate))}
                >
                  <span className={styles.rank}>{integer(index + 1)}</span>
                  <CategoryPath path={candidate.path} className={styles.category} />
                  <span className={styles.marker}>
                    {chosen ? (
                      <span className={styles.selection}>
                        <span className={styles.knot} aria-hidden="true" />
                        <StatusBadge
                          tone="success"
                          icon="check"
                          label={t("stand:progress.selected")}
                        />
                      </span>
                    ) : null}
                  </span>
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </Card>
  )
}
