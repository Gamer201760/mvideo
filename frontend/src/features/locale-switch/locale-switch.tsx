import { LOCALES, type Locale, useLocale, useTranslation } from "@/shared/i18n"
import { Segmented, type SegmentedOption } from "@/shared/ui"

export function LocaleSwitch() {
  const { t } = useTranslation()
  const { locale, setLocale } = useLocale()
  const options: SegmentedOption<Locale>[] = LOCALES.map((value) => ({
    value,
    label: t(`common:language.${value}`),
    short: t(`common:language.short.${value}`),
  }))
  return (
    <Segmented
      label={t("common:language.legend")}
      options={options}
      value={locale}
      display="short"
      onChange={setLocale}
    />
  )
}
