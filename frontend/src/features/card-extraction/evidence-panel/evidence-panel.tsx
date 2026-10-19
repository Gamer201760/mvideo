import { useEffect, useRef } from "react"
import { CardText, type ExtractResult } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"
import { ScrollArea, SidePanel } from "@/shared/ui"
import styles from "./evidence-panel.module.css"

export interface EvidencePanelProps {
  readonly id: string
  readonly open: boolean
  readonly result: ExtractResult
  readonly attribute: string | null
  readonly onClose: (instant?: boolean) => void
  readonly instant: boolean
}

export function EvidencePanel({
  id,
  open,
  result,
  attribute,
  onClose,
  instant,
}: EvidencePanelProps) {
  const { t } = useTranslation()
  const source = useRef<HTMLDivElement>(null)
  const values = [...result.values, ...(result.extra_values ?? [])]
  const selected = values.find((value) => value.attribute === attribute)

  useEffect(() => {
    if (!open || selected === undefined) return
    const frame = window.requestAnimationFrame(() => {
      const element = source.current
      const mark = element?.querySelector<HTMLElement>('[data-active="true"]')
      if (!element || !mark) return
      const line = mark.getBoundingClientRect()
      element.scrollTop += line.top - element.getBoundingClientRect().top - element.clientHeight / 2
    })
    return () => window.cancelAnimationFrame(frame)
  }, [open, selected])

  return (
    <SidePanel
      id={id}
      open={open}
      title={t("stand:result.textTitle")}
      closeLabel={t("stand:evidence.close")}
      onClose={onClose}
      instant={instant}
    >
      {selected === undefined ? null : (
        <div className={styles.selection}>
          <p className={styles.attribute} lang="ru">
            {selected.attribute}
          </p>
          <p className={styles.value} lang="ru">
            {selected.value}
          </p>
        </div>
      )}
      <ScrollArea
        className={styles.source}
        ref={source}
        data-evidence-scroll=""
        tabIndex={0}
        role="region"
        aria-label={t("stand:evidence.source")}
      >
        <CardText text={result.text} values={values} activeAttribute={attribute} />
      </ScrollArea>
    </SidePanel>
  )
}
