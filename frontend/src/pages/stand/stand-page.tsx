import { useState } from "react"
import { CardExtraction } from "@/features/card-extraction"
import { ReviewQueue } from "@/features/review-queue"
import { TextExtraction } from "@/features/text-extraction"
import { useDocumentTitle, useTranslation } from "@/shared/i18n"
import { PageHeader, Segmented } from "@/shared/ui"
import styles from "./stand-page.module.css"

type Mode = "card" | "text"

export function StandPage() {
  const { t } = useTranslation()
  const [refreshKey, setRefreshKey] = useState(0)
  const [mode, setMode] = useState<Mode>("card")
  useDocumentTitle(null)
  const queue = <ReviewQueue onResolved={() => setRefreshKey((key) => key + 1)} />
  return (
    <div className={styles.page}>
      <PageHeader title={t("stand:title")} description={t("stand:description")} />
      <Segmented
        label={t("stand:mode.label")}
        value={mode}
        onChange={setMode}
        options={[
          { value: "card", label: t("stand:mode.card") },
          { value: "text", label: t("stand:mode.text") },
        ]}
        className={styles.mode}
      />
      {mode === "card" ? (
        <CardExtraction refreshKey={refreshKey} sideSlot={queue} />
      ) : (
        <TextExtraction refreshKey={refreshKey} sideSlot={queue} />
      )}
    </div>
  )
}
