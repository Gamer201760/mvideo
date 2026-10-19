import { type ReactNode, useState } from "react"
import type { ResolveInput } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { TextField } from "@/shared/ui"

interface InlineValueProps {
  readonly attribute: string
  readonly value: string
  readonly input: ResolveInput
  readonly disabled: boolean
  readonly pending: boolean
  readonly error: ReactNode
  readonly onSave: (input: ResolveInput, onSaved: () => void) => void
}

export function InlineValue({
  attribute,
  value,
  input,
  disabled,
  pending,
  error,
  onSave,
}: InlineValueProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<{ value: string; input: ResolveInput } | null>(null)
  const save = () => {
    if (disabled || pending || draft === null) return
    const next = draft.value.trim()
    if (next === "" || next === value) setDraft(null)
    else onSave({ ...draft.input, value: next }, () => setDraft(null))
  }
  return (
    <TextField
      variant="inline"
      label={t("stand:review.editInline", { attribute })}
      value={draft?.value ?? value}
      onChange={(next) =>
        setDraft((previous) => ({ value: next, input: previous?.input ?? input }))
      }
      readOnly={pending || disabled}
      error={error}
      onBlur={save}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing || pending) return
        if (event.key === "Escape") {
          event.stopPropagation()
          setDraft(null)
        }
        if (event.key === "Enter") {
          event.preventDefault()
          save()
        }
      }}
    />
  )
}
