import { useErrorCopy, useTranslation } from "@/shared/i18n"
import { ErrorState } from "@/shared/ui"

export interface SavedResultNoticeProps {
  readonly fetching: boolean
  readonly error: unknown
  readonly onRetry: () => void
}

export function SavedResultNotice({ fetching, error, onRetry }: SavedResultNoticeProps) {
  const { t } = useTranslation()
  const errorCopy = useErrorCopy()
  if (!fetching && error == null) return null
  return (
    <div>
      <p role="status">{t(fetching ? "stand:workspace.checking" : "stand:workspace.unchecked")}</p>
      {error == null ? null : (
        <ErrorState {...errorCopy(error)} onRetry={onRetry} retryPending={fetching} />
      )}
    </div>
  )
}
