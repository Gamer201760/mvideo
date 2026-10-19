import { useState } from "react"
import { type ReviewItem, sourceKey } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, TextField } from "@/shared/ui"
import styles from "./review-row.module.css"

export interface ReviewRowProps {
  readonly item: ReviewItem
  readonly pending: boolean
  readonly disabled?: boolean
  readonly onAccept: () => void
  readonly onCorrect: (value: string) => void
}

export function ReviewRow({ item, pending, disabled, onAccept, onCorrect }: ReviewRowProps) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(item.value)

  return (
    <li id={`review-${item.id}`} tabIndex={-1} className={styles.row}>
      <div className={styles.head}>
        <span className={styles.attribute}>{item.attribute}</span>
        <span className={styles.meta}>
          {t("stand:review.confidence", {
            value: t("stand:risk.score", { value: Math.round(item.confidence * 100), max: 100 }),
          })}
        </span>
        <span className={styles.meta}>{t(sourceKey(item.source))}</span>
      </div>
      <p className={styles.value} lang="ru">
        {item.value}
      </p>
      <p className={styles.quote} lang="ru">
        {item.evidence}
      </p>
      <p className={styles.title} lang="ru">
        {item.title}
      </p>
      {editing ? (
        <form
          className={styles.edit}
          onSubmit={(event) => {
            event.preventDefault()
            if (!disabled) onCorrect(value)
          }}
        >
          <TextField
            label={t("stand:review.valueLabel", { attribute: item.attribute })}
            value={value}
            onChange={setValue}
            required
          />
          <div className={styles.actions}>
            <Button
              type="submit"
              icon="check"
              pending={pending}
              disabled={disabled || value.trim() === ""}
            >
              {t("stand:review.save")}
            </Button>
            <Button variant="ghost" disabled={disabled} onClick={() => setEditing(false)}>
              {t("stand:review.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <div className={styles.actions}>
          <Button
            size="compact"
            icon="check"
            pending={pending}
            disabled={disabled}
            onClick={onAccept}
          >
            {t("stand:review.accept")}
          </Button>
          <Button
            size="compact"
            variant="secondary"
            icon="correct"
            disabled={disabled}
            onClick={() => setEditing(true)}
          >
            {t("stand:review.correct")}
          </Button>
        </div>
      )}
    </li>
  )
}
