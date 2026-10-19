import { useDocumentTitle, useTranslation } from "@/shared/i18n"
import { ButtonLink, ErrorState } from "@/shared/ui"

export function NotFoundPage() {
  const { t } = useTranslation()
  useDocumentTitle(t("common:notFound.title"))
  return (
    <ErrorState
      layout="page"
      titleAs="h1"
      icon="unknown"
      title={t("common:notFound.title")}
      description={t("common:notFound.description")}
      action={
        <ButtonLink to="/" variant="secondary" icon="home">
          {t("common:action.home")}
        </ButtonLink>
      }
    />
  )
}
