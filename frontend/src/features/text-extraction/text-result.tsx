import { useState } from "react"
import { AttributeTable, CardText, MissingAttributes, type TextResult } from "@/entities/stand"
import { useErrorText, useFormatters, useTranslation } from "@/shared/i18n"
import { Swap, useLoadingIndicator } from "@/shared/motion"
import { Card, EmptyState, ErrorState, Skeleton } from "@/shared/ui"
import styles from "./text-result.module.css"
import { TextSummary } from "./text-summary/text-summary"

export interface TextResultViewProps {
  readonly result: TextResult | undefined
  readonly pending: boolean
  readonly error: unknown
  readonly onRetry: () => void
}

type View = "empty" | "loading" | "error" | "data"

function viewOf(props: TextResultViewProps): View {
  if (props.error !== null && props.error !== undefined) return "error"
  if (props.result !== undefined) return "data"
  return props.pending ? "loading" : "empty"
}

export function TextResultView(props: TextResultViewProps) {
  const { result, pending, error, onRetry } = props
  const { t } = useTranslation()
  const errorText = useErrorText()
  const { percent } = useFormatters()
  const [focused, setFocused] = useState<string | null>(null)
  const indicator = useLoadingIndicator({ pending, hasData: result !== undefined })
  const view = viewOf(props)
  const stale = indicator === "stale" || indicator === "spinner"
  const quoted = (result?.values ?? []).map((v) => ({ ...v, start: v.text_start, end: v.text_end }))

  return (
    <div className={styles.column}>
      <Card
        title={t("stand:result.title")}
        eyebrow={
          result === undefined
            ? undefined
            : t("stand:result.threshold", { value: percent(result.threshold) })
        }
        motionIndex={1}
        aria-busy={pending || undefined}
      >
        <div className={styles.body} data-stale={stale}>
          <Swap swapKey={view} as="div">
            {view === "empty" ? (
              <EmptyState
                icon="card"
                title={t("stand:result.empty.title")}
                description={t("stand:result.empty.description")}
              />
            ) : null}
            {view === "loading" ? (
              <div role="status" aria-label={t("stand:result.loading")}>
                {indicator === "skeleton" ? <Skeleton lines={6} /> : null}
              </div>
            ) : null}
            {view === "error" ? (
              <ErrorState title={errorText(error)} onRetry={onRetry} retryPending={pending} />
            ) : null}
            {view === "data" && result !== undefined ? (
              <div className={styles.data}>
                <TextSummary result={result} />
                <AttributeTable values={result.values} onFocusAttribute={setFocused} />
                <MissingAttributes names={result.missing} />
              </div>
            ) : null}
          </Swap>
        </div>
      </Card>
      {result === undefined ? null : (
        <Card title={t("stand:text.cleanTitle")} motionIndex={2}>
          <div className={styles.body} data-stale={stale}>
            <CardText text={result.text} values={quoted} activeAttribute={focused} />
          </div>
        </Card>
      )}
    </div>
  )
}
