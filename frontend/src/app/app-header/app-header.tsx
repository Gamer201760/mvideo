import { Link } from "react-router"
import { LocaleSwitch } from "@/features/locale-switch"
import { ThemeSwitch } from "@/features/theme-switch"
import { useTranslation } from "@/shared/i18n"
import styles from "./app-header.module.css"

export function AppHeader() {
  const { t } = useTranslation()
  return (
    <header className={styles.header}>
      <Link to="/" viewTransition className={styles.brand}>
        {t("common:app.name")}
      </Link>
      <div className={styles.controls}>
        <LocaleSwitch />
        <ThemeSwitch />
      </div>
    </header>
  )
}
