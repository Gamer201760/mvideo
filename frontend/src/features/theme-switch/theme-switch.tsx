import { useTranslation } from "@/shared/i18n"
import { THEMES, type Theme, useTheme } from "@/shared/theme"
import { type IconName, Segmented, type SegmentedOption, type SegmentedTone } from "@/shared/ui"

const THEME_ICON: Readonly<Record<Theme, IconName>> = {
  light: "theme-light",
  dark: "theme-dark",
}

export interface ThemeSwitchProps {
  readonly tone?: SegmentedTone
}

export function ThemeSwitch({ tone = "default" }: ThemeSwitchProps) {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const options: SegmentedOption<Theme>[] = THEMES.map((value) => ({
    value,
    label: t(`common:theme.${value}`),
    icon: THEME_ICON[value],
  }))
  return (
    <Segmented
      label={t("common:theme.legend")}
      options={options}
      value={theme}
      display="icon"
      tone={tone}
      onChange={setTheme}
    />
  )
}
