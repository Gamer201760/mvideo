import { useFormatters, useTranslation } from "@/shared/i18n"
import styles from "./missing-attributes.module.css"

export interface MissingAttributesProps {
  readonly names: readonly string[]
}

export function MissingAttributes({ names }: MissingAttributesProps) {
  const { t } = useTranslation()
  const { list } = useFormatters()
  return (
    <p className={styles.missing}>
      <span className={styles.label}>{t("stand:result.missingTitle")}</span>
      <span lang="ru">{names.length === 0 ? t("stand:result.missingNone") : list(names)}</span>
    </p>
  )
}
