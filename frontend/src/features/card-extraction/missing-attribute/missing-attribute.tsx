import { useEffect, useRef, useState } from "react"
import { type ExtractInput, useAddAttribute } from "@/entities/stand"
import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { Button, Disclosure, TextField } from "@/shared/ui"
import styles from "./missing-attribute.module.css"

interface MissingAttributeProps {
  readonly input: ExtractInput
  readonly attribute: string
  readonly text: string
  readonly disabled: boolean
}

export function MissingAttribute({ input, attribute, text, disabled }: MissingAttributeProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  const add = useAddAttribute()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState("")
  const [evidence, setEvidence] = useState("")
  const [checked, setChecked] = useState(false)
  const control = useRef<HTMLInputElement | HTMLTextAreaElement>(null)
  const root = useRef<HTMLDivElement>(null)
  const invalidQuote = evidence.trim() === "" || !text.includes(evidence)
  const locked = disabled || add.isPending
  useEffect(() => {
    if (open) control.current?.focus({ preventScroll: true })
  }, [open])
  const close = () => {
    setOpen(false)
    root.current?.querySelector<HTMLButtonElement>("button[aria-expanded]")?.focus()
  }
  return (
    <div className={styles.root} ref={root}>
      <Disclosure
        label={t("stand:review.addInline", { attribute })}
        icon="correct"
        open={open}
        onOpenChange={(next) => {
          if (locked) return
          setOpen(next)
          if (next) add.reset()
        }}
      >
        <form
          className={styles.form}
          aria-busy={add.isPending || undefined}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !locked) {
              event.stopPropagation()
              close()
            }
          }}
          onSubmit={(event) => {
            event.preventDefault()
            setChecked(true)
            if (locked || invalidQuote || value.trim() === "") return
            add.mutate(
              { card: input, attribute, value: value.trim(), evidence },
              {
                onSuccess: () =>
                  document.querySelector<HTMLElement>("[data-review-summary]")?.focus(),
              },
            )
          }}
        >
          <TextField
            label={t("stand:review.valueLabel", { attribute })}
            value={value}
            onChange={setValue}
            controlRef={control}
            required
          />
          <TextField
            label={t("stand:review.quoteLabel")}
            value={evidence}
            onChange={setEvidence}
            rows={3}
            hint={t("stand:review.quoteHint")}
            error={checked && invalidQuote ? t("stand:review.quoteInvalid") : undefined}
            required
          />
          <div className={styles.actions}>
            <Button
              type="submit"
              icon="check"
              pending={add.isPending}
              disabled={locked || value.trim() === ""}
            >
              {t("stand:review.save")}
            </Button>
            <Button variant="ghost" disabled={locked} onClick={close}>
              {t("stand:review.cancel")}
            </Button>
          </div>
          {add.isError ? (
            <p className={styles.error} role="alert">
              {errorCopy(add.error).description}
            </p>
          ) : null}
        </form>
      </Disclosure>
    </div>
  )
}
