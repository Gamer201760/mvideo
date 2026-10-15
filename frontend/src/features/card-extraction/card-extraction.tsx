import { type ReactNode, useEffect, useRef } from "react"
import { type ExtractInput, useExamples, useExtract, useStandInfo } from "@/entities/stand"
import { useErrorText, useTranslation } from "@/shared/i18n"
import { Card, ErrorState, Skeleton } from "@/shared/ui"
import styles from "./card-extraction.module.css"
import { CardForm } from "./card-form/card-form"
import { ExtractionResult } from "./extraction-result/extraction-result"

export interface CardExtractionProps {
  readonly refreshKey: number
  readonly sideSlot?: ReactNode
}

export function CardExtraction({ refreshKey, sideSlot }: CardExtractionProps) {
  const { t } = useTranslation()
  const errorText = useErrorText()
  const info = useStandInfo()
  const examples = useExamples()
  const extract = useExtract()
  const lastInput = useRef<ExtractInput | null>(null)
  const { mutate } = extract

  useEffect(() => {
    if (refreshKey > 0 && lastInput.current !== null) mutate(lastInput.current)
  }, [refreshKey, mutate])

  const run = (input: ExtractInput) => {
    lastInput.current = input
    mutate(input)
  }
  const retry = () => {
    if (lastInput.current !== null) mutate(lastInput.current)
  }
  const sourcesError = info.error ?? examples.error

  return (
    <div className={styles.extraction}>
      <div className={styles.side}>
        {sourcesError !== null ? (
          <Card title={t("stand:form.title")} motionIndex={0}>
            <ErrorState
              title={errorText(sourcesError)}
              onRetry={() => {
                void info.refetch()
                void examples.refetch()
              }}
              retryPending={info.isFetching || examples.isFetching}
            />
          </Card>
        ) : info.data === undefined || examples.data === undefined ? (
          <Card title={t("stand:form.title")} motionIndex={0} aria-busy>
            <div role="status" aria-label={t("common:state.loading")}>
              <Skeleton lines={8} />
            </div>
          </Card>
        ) : (
          <CardForm
            categories={info.data.categories}
            examples={examples.data.items}
            pending={extract.isPending}
            onSubmit={run}
          />
        )}
        {sideSlot}
      </div>
      <ExtractionResult
        result={extract.data}
        pending={extract.isPending}
        error={extract.error}
        onRetry={retry}
      />
    </div>
  )
}
