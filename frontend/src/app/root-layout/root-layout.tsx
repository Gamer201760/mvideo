import { Outlet, ScrollRestoration } from "react-router"
import { useTranslation } from "@/shared/i18n"
import { AppHeader } from "../app-header/app-header"
import styles from "./root-layout.module.css"
import { useRouteFocus } from "./use-route-focus"

export function RootLayout() {
  const { t } = useTranslation()
  useRouteFocus()
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main">
        {t("common:shell.skip")}
      </a>
      <AppHeader />
      <main id="main" tabIndex={-1} className={styles.main}>
        <Outlet />
      </main>
      <ScrollRestoration />
    </div>
  )
}
