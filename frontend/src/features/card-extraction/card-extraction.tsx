import { type ReactNode, useEffect, useRef } from "react"
import type {
  AttributeReviewSlots,
  ExtractInput,
  ExtractResult,
  RunDetail,
  StandCategory,
} from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, Card, Spinner } from "@/shared/ui"
import { CardCompletion } from "./card-completion/card-completion"
import styles from "./card-extraction.module.css"
import { CardSources } from "./card-sources/card-sources"
import { ExtractionProgress } from "./extraction-progress/extraction-progress"
import { useSelectionReveal } from "./extraction-progress/use-selection-reveal"
import { ExtractionResult } from "./extraction-result/extraction-result"
import { useInlineReview } from "./inline-review/use-inline-review"
import { InterruptedRun } from "./interrupted-run/interrupted-run"
import { SavedResultNotice } from "./saved-result-notice/saved-result-notice"
import { useCardWorkspace } from "./use-card-workspace"
import { WorkspaceBar } from "./workspace-bar/workspace-bar"

export interface CardExtractionProps {
  readonly historySlot: (onOpen: (run: RunDetail) => void) => ReactNode
  readonly exportSlot: (input: ExtractInput, result: ExtractResult) => ReactNode
}

export function CardExtraction({ historySlot, exportSlot }: CardExtractionProps) {
  const { t } = useTranslation()
  const state = useCardWorkspace()
  const { started, pending, restored, runId, input, result, run, retry } = state
  const { startRef, titleRef } = useWorkspaceFocus(started, runId)
  const reviewSlots = useInlineReview(
    state.reviews.data,
    pending || state.reviews.isFetching,
    result?.auto_accept_enabled === false,
  )
  return (
    <div className={styles.extraction} data-started={started}>
      <div className={styles.start} hidden={started} ref={startRef}>
        <CardSources key={state.draftId} pending={pending} onSubmit={run} />
        {state.workspace.completed === null ? null : (
          <Button variant="ghost" disabled={pending} onClick={state.showCompleted}>
            {t("stand:workspace.previous")}
          </Button>
        )}
        {started ? null : historySlot(state.openRun)}
      </div>
      {started ? (
        state.interrupted ? (
          <InterruptedRun
            title={input?.title ?? ""}
            hasResult={state.workspace.completed !== null}
            onResume={retry}
            onPrevious={state.showCompleted}
            onDraft={state.openDraft}
          />
        ) : (
          <div className={styles.workspace}>
            <WorkspaceBar
              title={input?.title ?? ""}
              engine={input?.engine ?? "hybrid"}
              pending={pending}
              titleRef={titleRef}
              onNew={state.openDraft}
            />
            {restored ? (
              <SavedResultNotice
                fetching={state.reviews.isFetching}
                error={state.reviews.error}
                onRetry={() => void state.reviews.refetch()}
              />
            ) : null}
            <WorkspaceResults
              key={runId}
              hybrid={input?.engine === "hybrid" && !restored}
              candidates={state.candidates}
              result={result}
              pending={pending}
              error={state.error}
              onRetry={retry}
              reviewSlots={reviewSlots}
              input={input}
              completion={
                <CardCompletion
                  input={input}
                  result={result}
                  reviews={state.reviews.data}
                  disabled={state.reviews.isFetching || state.reviews.isError}
                />
              }
              exportSlot={exportSlot}
            />
          </div>
        )
      ) : null}
    </div>
  )
}

function useWorkspaceFocus(started: boolean, runId: number) {
  const startRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    if (runId === 0) return
    if (started) titleRef.current?.focus()
    else startRef.current?.querySelector<HTMLElement>("input, textarea")?.focus()
  }, [started, runId])

  return { startRef, titleRef }
}

interface WorkspaceResultsProps {
  readonly hybrid: boolean
  readonly candidates: readonly StandCategory[] | undefined
  readonly result: ExtractResult | undefined
  readonly pending: boolean
  readonly error: unknown
  readonly onRetry: () => void
  readonly reviewSlots: AttributeReviewSlots
  readonly input: ExtractInput | undefined
  readonly completion: ReactNode
  readonly exportSlot: CardExtractionProps["exportSlot"]
}

function WorkspaceResults({
  hybrid,
  candidates,
  result,
  pending,
  error,
  onRetry,
  reviewSlots,
  input,
  completion,
  exportSlot,
}: WorkspaceResultsProps) {
  const { t } = useTranslation()
  const reveal = useSelectionReveal(candidates?.length, result !== undefined && !pending)
  const failed = error !== null
  const ranking = hybrid && !failed && reveal !== "complete"
  const exportAction =
    input === undefined || result === undefined ? null : exportSlot(input, result)
  const chosen = result?.category
  const rankedCandidates =
    reveal !== "ranking" &&
    chosen != null &&
    !candidates?.some((candidate) => candidate.category_id === chosen.category_id)
      ? [chosen, ...(candidates ?? []).slice(0, 4)]
      : candidates
  return (
    <div className={styles.results}>
      {ranking ? (
        <ExtractionProgress
          candidates={rankedCandidates}
          pending={pending}
          selected={reveal === "ranking" ? undefined : (result?.category?.category_id ?? null)}
        />
      ) : !pending || failed ? (
        <ExtractionResult
          result={result}
          pending={false}
          error={error}
          onRetry={onRetry}
          reviewSlots={reviewSlots}
          exportAction={exportAction}
          sideSlot={completion}
        />
      ) : (
        <Card title={t("stand:result.loading")}>
          <Spinner label={t("stand:result.loading")} />
        </Card>
      )}
    </div>
  )
}
