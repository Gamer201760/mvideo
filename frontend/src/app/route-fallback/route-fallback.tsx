import { useTranslation } from "@/shared/i18n"
import { Skeleton } from "@/shared/ui"
import styles from "./route-fallback.module.css"

export function RouteFallback() {
  const { t } = useTranslation()
  return (
    <div className={styles.fallback} role="status" aria-label={t("common:state.loading")}>
      <Skeleton lines={2} className={styles.heading} />
      <Skeleton shape="block" />
      <Skeleton shape="block" />
    </div>
  )
}
