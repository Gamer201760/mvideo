import { HealthCard } from "@/entities/health"
import { useDocumentTitle, useTranslation } from "@/shared/i18n"
import { Card, EmptyState, PageHeader } from "@/shared/ui"
import { FormatSamples } from "./format-samples/format-samples"
import styles from "./home-page.module.css"

export function HomePage() {
  const { t } = useTranslation()
  useDocumentTitle(null)
  return (
    <div className={styles.page}>
      <PageHeader title={t("home:title")} description={t("home:description")} />
      <div className={styles.panels}>
        <FormatSamples motionIndex={0} />
        <HealthCard motionIndex={1} />
        <Card as="div" motionIndex={2}>
          <EmptyState
            icon="empty"
            title={t("home:empty.title")}
            description={t("home:empty.description")}
          />
        </Card>
      </div>
    </div>
  )
}
