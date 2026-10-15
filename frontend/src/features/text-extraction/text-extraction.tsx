import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react"
import { type TextInput, useExtractText } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { Button, Card, TextField } from "@/shared/ui"
import styles from "./text-extraction.module.css"
import { TextResultView } from "./text-result"

export interface TextExtractionProps {
  readonly refreshKey: number
  readonly sideSlot?: ReactNode
}

export function TextExtraction({ refreshKey, sideSlot }: TextExtractionProps) {
  const { t } = useTranslation()
  const extract = useExtractText()
  const [text, setText] = useState("")
  const lastInput = useRef<TextInput | null>(null)
  const { mutate } = extract

  useEffect(() => {
    if (refreshKey > 0 && lastInput.current !== null) mutate(lastInput.current)
  }, [refreshKey, mutate])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    lastInput.current = { text }
    mutate(lastInput.current)
  }
  const retry = () => {
    if (lastInput.current !== null) mutate(lastInput.current)
  }

  return (
    <div className={styles.extraction}>
      <div className={styles.side}>
        <Card title={t("stand:text.title")} motionIndex={0}>
          <form className={styles.form} onSubmit={submit}>
            <TextField
              label={t("stand:text.field")}
              placeholder={t("stand:text.placeholder")}
              hint={t("stand:text.hint")}
              value={text}
              onChange={setText}
              rows={14}
              mono
              required
            />
            <Button
              type="submit"
              icon="extract"
              pending={extract.isPending}
              disabled={text.trim() === ""}
            >
              {t("stand:text.submit")}
            </Button>
          </form>
        </Card>
        {sideSlot}
      </div>
      <TextResultView
        result={extract.data}
        pending={extract.isPending}
        error={extract.error}
        onRetry={retry}
      />
    </div>
  )
}
