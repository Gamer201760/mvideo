import { useDocumentTitle, useTranslation } from "@/shared/i18n"
import { ButtonLink, PageHeader } from "@/shared/ui"

export function NotFoundPage() {
  const { t } = useTranslation()
  useDocumentTitle(t("common:notFound.title"))
  return (
    <PageHeader
      title={t("common:notFound.title")}
      description={t("common:notFound.description")}
      actions={
        <ButtonLink to="/" icon="home">
          {t("common:action.home")}
        </ButtonLink>
      }
    />
  )
}
