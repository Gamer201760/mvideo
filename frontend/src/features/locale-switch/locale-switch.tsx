import { LOCALES, type Locale, useLocale, useTranslation } from "@/shared/i18n"
import { Segmented, type SegmentedOption, type SegmentedTone } from "@/shared/ui"

export interface LocaleSwitchProps {
  readonly tone?: SegmentedTone
}

export function LocaleSwitch({ tone = "default" }: LocaleSwitchProps) {
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
      tone={tone}
      onChange={setLocale}
    />
  )
}
