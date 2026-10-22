import { useTranslation } from "@/shared/i18n"
import { StatusBadge } from "@/shared/ui"
import styles from "./fallback-notice.module.css"

export interface FallbackNoticeProps {
  readonly reason: string | null | undefined
}

export function FallbackNotice({ reason }: FallbackNoticeProps) {
  const { t } = useTranslation()
  if (!reason) return null
  return (
    <div className={styles.notice} role="status">
      <StatusBadge tone="warning" icon="alert" label={t("stand:result.fallbackTitle")} />
      <p className={styles.description}>{t("stand:result.fallbackDescription")}</p>
    </div>
  )
}
