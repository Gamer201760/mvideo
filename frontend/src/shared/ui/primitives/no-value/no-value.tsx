import { useTranslation } from "../../../i18n"
import styles from "./no-value.module.css"

export interface NoValueProps {
  readonly label?: string | undefined
}

export function NoValue({ label }: NoValueProps) {
  const { t } = useTranslation()
  return (
    <span className={styles.none} data-no-value="">
      <span aria-hidden="true">{t("common:value.none")}</span>
      <span className="visually-hidden">{label ?? t("common:value.noneLabel")}</span>
    </span>
  )
}
