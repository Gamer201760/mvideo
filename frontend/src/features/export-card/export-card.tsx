import { type CardExportSource, useCardExport } from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { Button, ErrorState } from "@/shared/ui"
import { downloadCard } from "./download-card"
import styles from "./export-card.module.css"

export interface ExportCardProps {
  readonly source: CardExportSource
  readonly compact?: boolean
}

export function ExportCard({ source, compact = false }: ExportCardProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const mutation = useCardExport()
  const save = () => mutation.mutate(source, { onSuccess: downloadCard })
  return (
    <div className={styles.export}>
      <Button
        variant="secondary"
        size={compact ? "compact" : "regular"}
        icon="download"
        pending={mutation.isPending}
        onClick={save}
      >
        {t("stand:export.download")}
      </Button>
      {mutation.isError ? (
        <ErrorState
          title={t("stand:export.failed")}
          description={errorCopy(mutation.error).description}
          onRetry={save}
          retryPending={mutation.isPending}
        />
      ) : null}
    </div>
  )
}
