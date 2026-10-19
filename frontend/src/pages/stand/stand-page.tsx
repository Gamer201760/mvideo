import { CardExtraction } from "@/features/card-extraction"
import { ExportCard } from "@/features/export-card"
import { RunHistory } from "@/features/run-history"
import { useDocumentTitle, useTranslation } from "@/shared/i18n"
import { PageHeader } from "@/shared/ui"
import styles from "./stand-page.module.css"

export function StandPage() {
  const { t } = useTranslation()
  useDocumentTitle(null)
  return (
    <div className={styles.page}>
      <div className="visually-hidden">
        <PageHeader title={t("stand:title")} />
      </div>
      <CardExtraction
        exportSlot={(input, result) => <ExportCard source={{ input, result }} />}
        historySlot={(onOpen) => (
          <RunHistory
            onOpen={onOpen}
            exportSlot={(run) => <ExportCard source={{ runId: run.id }} compact />}
          />
        )}
      />
    </div>
  )
}
