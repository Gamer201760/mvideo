import { useTranslation } from "@/shared/i18n"
import { Button, Card } from "@/shared/ui"

export interface InterruptedRunProps {
  readonly title: string
  readonly hasResult: boolean
  readonly onResume: () => void
  readonly onPrevious: () => void
  readonly onDraft: () => void
}

export function InterruptedRun({
  title,
  hasResult,
  onResume,
  onPrevious,
  onDraft,
}: InterruptedRunProps) {
  const { t } = useTranslation()
  return (
    <Card
      title={t("stand:workspace.interrupted")}
      description={t("stand:workspace.interruptedDescription")}
    >
      <p lang="ru">{title}</p>
      <Button icon="extract" onClick={onResume}>
        {t("stand:workspace.resume")}
      </Button>
      {hasResult ? (
        <Button variant="secondary" onClick={onPrevious}>
          {t("stand:workspace.previous")}
        </Button>
      ) : null}
      <Button variant="ghost" onClick={onDraft}>
        {t("stand:form.back")}
      </Button>
    </Card>
  )
}
