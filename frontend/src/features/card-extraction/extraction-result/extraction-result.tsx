import { type ReactNode, useId, useRef } from "react"
import {
  type AttributeReviewSlots,
  AttributeTable,
  CategoryPath,
  type ExtractResult,
} from "@/entities/stand"
import { useErrorCopy, useFormatters, useTranslation } from "@/shared/i18n"
import { Swap, ThreadLayer, useLoadingIndicator } from "@/shared/motion"
import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/shared/ui"
import { EvidencePanel } from "../evidence-panel/evidence-panel"
import { FallbackNotice } from "../fallback-notice/fallback-notice"
import { RejectedFields } from "../rejected-fields/rejected-fields"
import styles from "./extraction-result.module.css"
import { useEvidenceDisclosure } from "./use-evidence-disclosure"
import { useResultLabels } from "./use-result-labels"

export interface ExtractionResultProps {
  readonly result: ExtractResult | undefined
  readonly pending: boolean
  readonly error: unknown
  readonly onRetry: () => void
  readonly sideSlot?: ReactNode
  readonly exportAction?: ReactNode
  readonly reviewSlots?: AttributeReviewSlots | undefined
}

type View = "empty" | "loading" | "error" | "data"

interface FocusProps {
  readonly focused: string | null
  readonly onOpenEvidence: (attribute: string, instant: boolean) => void
  readonly evidencePanelId: string
  readonly reviewSlots?: AttributeReviewSlots | undefined
}

function viewOf(props: ExtractionResultProps): View {
  if (props.error !== null && props.error !== undefined) return "error"
  if (props.result !== undefined) return "data"
  return props.pending ? "loading" : "empty"
}

export function ExtractionResult(props: ExtractionResultProps) {
  const { result, pending, error, onRetry, sideSlot, exportAction, reviewSlots } = props
  const extraValues = result?.extra_values ?? []
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const board = useRef<HTMLDivElement>(null)
  const {
    focused,
    open: panelOpen,
    instant,
    panel,
    close: closePanel,
    show: openEvidence,
  } = useEvidenceDisclosure()
  const evidencePanelId = useId()
  const indicator = useLoadingIndicator({ pending, hasData: result !== undefined })
  const view = viewOf(props)
  const stale = indicator === "stale" || indicator === "spinner"
  const labels = useResultLabels(result)
  const activeAttribute = panelOpen ? focused : null

  return (
    <div className={styles.board} ref={board} data-evidence={panel.mounted}>
      <div className={styles.column}>
        <Card
          title={t("stand:result.title")}
          eyebrow={labels.threshold}
          actions={
            result === undefined ? undefined : (
              <>
                {exportAction}
                <Button
                  variant="secondary"
                  icon="card"
                  aria-controls={evidencePanelId}
                  aria-expanded={panelOpen}
                  onClick={(event) => openEvidence(null, event.detail === 0)}
                >
                  {t("stand:evidence.open")}
                </Button>
              </>
            )
          }
          motionIndex={0}
          aria-busy={pending || undefined}
          data-thread-lane=""
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
                <ErrorState {...errorCopy(error)} onRetry={onRetry} retryPending={pending} />
              ) : null}
              {view === "data" && result !== undefined ? (
                <ResultData
                  result={result}
                  focused={activeAttribute}
                  onOpenEvidence={openEvidence}
                  evidencePanelId={evidencePanelId}
                  reviewSlots={reviewSlots}
                />
              ) : null}
            </Swap>
          </div>
        </Card>
        <AdditionalFields
          values={extraValues}
          focused={activeAttribute}
          onOpenEvidence={openEvidence}
          evidencePanelId={evidencePanelId}
          reviewSlots={reviewSlots}
        />
        {sideSlot}
      </div>
      {result === undefined ? null : (
        <EvidencePanel
          id={evidencePanelId}
          open={panelOpen}
          result={result}
          attribute={focused}
          onClose={closePanel}
          instant={instant}
        />
      )}
      <ThreadLayer root={board} activeKey={activeAttribute} instant={instant} />
    </div>
  )
}

function ResultData({
  result,
  focused,
  onOpenEvidence,
  evidencePanelId,
  reviewSlots,
}: FocusProps & { readonly result: ExtractResult }) {
  const { t } = useTranslation()
  const { list } = useFormatters()
  const missing =
    result.missing.length > 0
      ? list(result.missing)
      : result.engine === "hybrid" && result.category == null
        ? t("stand:result.categoryUnknown")
        : (result.rejections?.length ?? 0) > 0
          ? t("stand:result.missingUnconfirmed")
          : result.category?.attributes.length === 0
            ? t("stand:result.requiredUnknown")
            : t("stand:result.missingNone")
  return (
    <div className={styles.data}>
      <FallbackNotice reason={result.fallback_reason} />
      {result.category == null ? null : (
        <p className={styles.category}>
          <span className={styles.label}>{t("stand:result.category")}</span>
          <CategoryPath path={result.category.path} />
        </p>
      )}
      <p className={styles.missing}>{t("stand:risk.description")}</p>
      <AttributeTable
        values={result.values}
        activeAttribute={focused}
        onOpenEvidence={onOpenEvidence}
        evidencePanelId={evidencePanelId}
        reviewSlots={reviewSlots}
      />
      <p className={styles.missing}>
        <span className={styles.label}>{t("stand:result.missingTitle")}</span>
        <span lang={result.missing.length > 0 ? "ru" : undefined}>{missing}</span>
      </p>
      <RejectedFields rejections={result.rejections} />
    </div>
  )
}

function AdditionalFields({
  values,
  focused,
  onOpenEvidence,
  evidencePanelId,
  reviewSlots,
}: FocusProps & { readonly values: ExtractResult["values"] }) {
  const { t } = useTranslation()
  if (values.length === 0) return null
  return (
    <Card title={t("stand:result.extraTitle")} motionIndex={2} data-thread-lane="">
      <AttributeTable
        values={values}
        activeAttribute={focused}
        onOpenEvidence={onOpenEvidence}
        evidencePanelId={evidencePanelId}
        reviewSlots={reviewSlots}
      />
    </Card>
  )
}
