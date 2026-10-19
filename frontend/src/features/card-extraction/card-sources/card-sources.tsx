import { type ExtractInput, useExamples, useStandInfo } from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { ButtonLink, Card, ErrorState, Skeleton } from "@/shared/ui"
import { CardForm } from "../card-form/card-form"
import { ExtractionIntro } from "../extraction-intro/extraction-intro"
import styles from "./card-sources.module.css"

export interface CardSourcesProps {
  readonly pending: boolean
  readonly onSubmit: (input: ExtractInput) => void
}

export function CardSources({ pending, onSubmit }: CardSourcesProps) {
  return (
    <div className={styles.landing}>
      <ExtractionIntro />
      <div className={styles.formSlot}>
        <SourceForm pending={pending} onSubmit={onSubmit} />
      </div>
    </div>
  )
}

function SourceForm({ pending, onSubmit }: CardSourcesProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const info = useStandInfo()
  const examples = useExamples()
  const error = info.error ?? examples.error
  if (error !== null) {
    return (
      <Card title={t("stand:form.title")}>
        <ErrorState
          {...errorCopy(error)}
          onRetry={() => {
            void info.refetch()
            void examples.refetch()
          }}
          retryPending={info.isFetching || examples.isFetching}
          action={
            <ButtonLink to="/status" variant="ghost" icon="status">
              {t("common:action.status")}
            </ButtonLink>
          }
        />
      </Card>
    )
  }
  if (info.data === undefined || examples.data === undefined) {
    return (
      <Card title={t("stand:form.title")} motionIndex={0}>
        <Skeleton lines={5} />
      </Card>
    )
  }
  return (
    <CardForm
      categories={info.data.categories}
      examples={examples.data.items}
      pending={pending}
      onSubmit={onSubmit}
    />
  )
}
