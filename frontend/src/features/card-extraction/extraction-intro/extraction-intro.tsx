import { useTranslation } from "@/shared/i18n"
import { Intro } from "@/shared/ui"
import styles from "./extraction-intro.module.css"
import { ExtractionVisual } from "./extraction-visual"

export function ExtractionIntro() {
  const { t } = useTranslation()
  return (
    <div className={styles.intro}>
      <Intro title={t("stand:landing.title")} description={t("stand:landing.description")}>
        <ExtractionVisual />
      </Intro>
    </div>
  )
}
