import { Link } from "react-router"
import { LocaleSwitch } from "@/features/locale-switch"
import { ThemeSwitch } from "@/features/theme-switch"
import { useTranslation } from "@/shared/i18n"
import { BrandLockup } from "@/shared/ui"
import styles from "./app-header.module.css"

export function AppHeader() {
  const { t } = useTranslation()
  return (
    <header className={styles.header}>
      <Link to="/" viewTransition className={styles.brand} aria-label={t("common:shell.home")}>
        <BrandLockup
          name={t("common:app.name")}
          partnerPrefix={t("common:shell.for")}
          partnerName={t("common:shell.partner")}
        />
      </Link>
      <div className={styles.controls}>
        <LocaleSwitch tone="inverse" />
        <ThemeSwitch tone="inverse" />
      </div>
    </header>
  )
}
