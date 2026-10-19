import { useState } from "react"
import { useTranslation } from "@/shared/i18n"
import { Button, CardFlow } from "@/shared/ui"
import styles from "./extraction-visual.module.css"

export function ExtractionVisual() {
  const { t } = useTranslation()
  const [paused, setPaused] = useState(false)
  return (
    <div className={styles.visual} data-paused={paused}>
      <CardFlow
        sourceTitle={t("stand:landing.sourceTitle")}
        resultTitle={t("stand:landing.resultTitle")}
      />
      <div className={styles.caption}>
        <p>{t("stand:landing.caption")}</p>
        <Button
          variant="ghost"
          icon={paused ? "play" : "pause"}
          onClick={() => setPaused((value) => !value)}
          aria-pressed={paused}
        >
          {t(paused ? "stand:landing.resume" : "stand:landing.pause")}
        </Button>
      </div>
    </div>
  )
}
