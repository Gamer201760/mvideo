import { useState } from "react"
import {
  type ExtractInput,
  type RunDetail,
  reconcileReviews,
  useCardReviews,
  useCategoryPreview,
  useExtract,
} from "@/entities/stand"
import { withViewTransition } from "@/shared/motion"
import { type CardWorkspace, readWorkspace, saveWorkspace } from "./card-storage"

export function useCardWorkspace() {
  const [workspace, setWorkspace] = useState(readWorkspace)
  const [interrupted, setInterrupted] = useState(workspace.pending !== null)
  const [restored, setRestored] = useState(workspace.completed !== null)
  const [runId, setRunId] = useState(0)
  const [draftId, setDraftId] = useState(0)
  const extract = useExtract()
  const preview = useCategoryPreview()
  const pending = preview.isPending || extract.isPending
  const input = workspace.pending ?? workspace.completed?.input
  const completed = workspace.pending === null ? workspace.completed : null
  const request =
    completed === null
      ? undefined
      : {
          ...completed.input,
          category_id:
            completed.result.category?.category_id ?? completed.input.category_id ?? null,
        }
  const reviews = useCardReviews(request)
  const result =
    completed === null
      ? undefined
      : reviews.data === undefined
        ? completed.result
        : reconcileReviews(completed.result, reviews.data.items)

  const persist = (next: CardWorkspace) => {
    saveWorkspace(next)
    setWorkspace(next)
  }
  const run = (card: ExtractInput) => {
    if (pending) return
    const next: CardWorkspace = { ...workspace, pending: card, view: "result" }
    persist(next)
    setInterrupted(false)
    setRestored(false)
    void withViewTransition("stage", () => {
      setRunId((value) => value + 1)
      extract.reset()
      preview.reset()
      const execute = () =>
        extract.mutate(card, {
          onSuccess: (received) =>
            persist({
              completed: { input: card, result: received },
              pending: null,
              view: "result",
            }),
        })
      if (card.engine === "hybrid") preview.mutate(card, { onSuccess: execute })
      else execute()
    })
  }
  const showCompleted = () => {
    persist({ ...workspace, pending: null, view: "result" })
    setInterrupted(false)
    setRestored(true)
    extract.reset()
    preview.reset()
  }
  const openDraft = () =>
    void withViewTransition("stage", () => {
      persist({ ...workspace, view: "draft" })
      setDraftId((value) => value + 1)
    })

  const openRun = (run: RunDetail) =>
    void withViewTransition("stage", () => {
      persist({
        completed:
          run.result === null ? workspace.completed : { input: run.input, result: run.result },
        pending: run.result === null ? run.input : null,
        view: "result",
      })
      setInterrupted(run.result === null)
      setRestored(true)
      setRunId((value) => value + 1)
      extract.reset()
      preview.reset()
    })

  return {
    workspace,
    input,
    result,
    reviews,
    pending,
    restored,
    runId,
    draftId,
    run,
    showCompleted,
    openDraft,
    openRun,
    started: workspace.view === "result",
    interrupted: interrupted && workspace.pending !== null,
    candidates: preview.data?.candidates,
    error: preview.error ?? extract.error,
    retry: () => {
      if (input !== undefined) run(input)
    },
  }
}
