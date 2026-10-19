import type { ExtractResult } from "@/entities/stand"
import { useTranslation } from "@/shared/i18n"

export function useResultLabels(result: ExtractResult | undefined) {
  const { t } = useTranslation()
  return {
    threshold:
      result?.engine === "hybrid" && result.auto_accept_enabled === false
        ? t("stand:result.manualMode")
        : result?.threshold == null
          ? undefined
          : t("stand:result.threshold", {
              value: t("stand:risk.score", { value: Math.round(result.threshold * 100), max: 100 }),
            }),
  }
}
