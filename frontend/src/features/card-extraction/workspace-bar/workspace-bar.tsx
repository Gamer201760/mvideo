import type { Ref } from "react"
import { useTranslation } from "@/shared/i18n"
import { Button, Icon, StatusBadge } from "@/shared/ui"
import styles from "./workspace-bar.module.css"

export interface WorkspaceBarProps {
  readonly title: string
  readonly engine: "rules" | "hybrid"
  readonly pending: boolean
  readonly onNew: () => void
  readonly titleRef?: Ref<HTMLParagraphElement> | undefined
}

export function WorkspaceBar({ title, engine, pending, onNew, titleRef }: WorkspaceBarProps) {
  const { t } = useTranslation()
  return (
    <div className={styles.bar}>
      <div className={styles.subject}>
        <Icon name="card" size="md" className={styles.icon} />
        <p className={styles.title} lang="ru" ref={titleRef} tabIndex={-1}>
          {title}
        </p>
        <StatusBadge
          tone="neutral"
          icon="extract"
          label={engine === "hybrid" ? t("stand:form.hybrid") : t("stand:form.rules")}
        />
      </div>
      <Button variant="ghost" size="compact" icon="back" disabled={pending} onClick={onNew}>
        {t("stand:form.back")}
      </Button>
    </div>
  )
}
