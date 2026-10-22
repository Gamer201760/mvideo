import { useEffect, useRef } from "react"
import {
  type AttributeReviewSlots,
  type CardReviewState,
  type ExtractedValue,
  type ResolveInput,
  useResolveReview,
} from "@/entities/stand"
import { useErrorCopy } from "@/shared/i18n"
import { InlineActions } from "./inline-actions"
import { InlineValue } from "./inline-value"

export function useInlineReview(
  card: CardReviewState | undefined,
  disabled: boolean,
  manualMode = false,
): AttributeReviewSlots {
  const errorCopy = useErrorCopy()
  const resolve = useResolveReview()
  const saving = useRef(false)
  const focused = useRef<HTMLElement | null>(null)
  useEffect(() => {
    const trackFocus = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && event.target !== document.body)
        focused.current = event.target
    }
    document.addEventListener("focusin", trackFocus)
    return () => document.removeEventListener("focusin", trackFocus)
  }, [])
  const inputFor = (value: ExtractedValue): ResolveInput | null => {
    const item =
      card?.items.find((item) => item.id === value.review_id) ??
      card?.items.find(
        (item) => item.attribute === value.attribute && item.evidence === value.evidence,
      )
    const id = item?.id ?? value.review_id
    if (id == null) return null
    return item?.status !== undefined &&
      item.status !== "pending" &&
      item.status !== "auto_accepted"
      ? { id, action: "correct", override: true, expectedValue: item.resolved_value ?? value.value }
      : { id, action: "correct" }
  }
  const act = (input: ResolveInput, onSaved?: () => void) => {
    if (disabled || saving.current) return
    saving.current = true
    resolve.mutate(input, {
      onSuccess: () => {
        onSaved?.()
        if (document.activeElement === document.body && focused.current?.isConnected)
          focused.current.focus({ preventScroll: true })
      },
      onSettled: () => {
        saving.current = false
      },
    })
  }
  const errorFor = (id: string | undefined, action: ResolveInput["action"]) =>
    resolve.isError && resolve.variables.id === id && resolve.variables.action === action
      ? errorCopy(resolve.error).description
      : undefined

  return {
    value: (value) => {
      const input = inputFor(value)
      if (input === null) return value.value
      return (
        <InlineValue
          key={input.id}
          attribute={value.attribute}
          value={value.value}
          input={input}
          disabled={disabled}
          pending={resolve.isPending}
          error={errorFor(input.id, "correct")}
          onSave={act}
        />
      )
    },
    actions: (value) => {
      const input = inputFor(value)
      return (
        <InlineActions
          value={value}
          input={input}
          manualMode={manualMode}
          disabled={disabled || resolve.isPending}
          pendingAction={
            resolve.isPending && resolve.variables.id === input?.id
              ? resolve.variables.action
              : undefined
          }
          error={errorFor(input?.id, "reject") ?? errorFor(input?.id, "accept")}
          onAct={(request) =>
            act(request, () =>
              document.querySelector<HTMLElement>("[data-review-summary]")?.focus(),
            )
          }
        />
      )
    },
  }
}
