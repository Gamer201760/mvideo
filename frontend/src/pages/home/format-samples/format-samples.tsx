import type { ReactNode } from "react"
import { useFormatters, useTranslation } from "@/shared/i18n"
import { Card, NoValue } from "@/shared/ui"
import styles from "./format-samples.module.css"

const SAMPLE_NUMBER = 1234567.891
const SAMPLE_SHARE = 0.427
const SAMPLE_AMOUNT = 1234567.5
const SAMPLE_CURRENCY = "RUB"
const SAMPLE_DATE = Date.UTC(2026, 2, 14, 9, 30)
const SAMPLE_COUNT = 1234

interface Term {
  readonly key: string
  readonly label: string
  readonly value: ReactNode
}

export interface FormatSamplesProps {
  readonly motionIndex?: number | undefined
}

export function FormatSamples({ motionIndex }: FormatSamplesProps) {
  const { t } = useTranslation()
  const format = useFormatters()
  const terms: readonly Term[] = [
    { key: "number", label: t("home:formats.number"), value: format.number(SAMPLE_NUMBER, 2) },
    { key: "percent", label: t("home:formats.percent"), value: format.percent(SAMPLE_SHARE, 1) },
    {
      key: "money",
      label: t("home:formats.money"),
      value: format.money(SAMPLE_AMOUNT, SAMPLE_CURRENCY),
    },
    { key: "date", label: t("home:formats.date"), value: format.date(SAMPLE_DATE) },
    {
      key: "count",
      label: t("home:formats.count"),
      value: t("home:formats.records", { count: SAMPLE_COUNT }),
    },
    { key: "missing", label: t("home:formats.missing"), value: <NoValue /> },
  ]
  return (
    <Card
      title={t("home:formats.title")}
      description={t("home:formats.description")}
      motionIndex={motionIndex}
    >
      <dl className={styles.terms}>
        {terms.map((term) => (
          <div key={term.key} className={styles.term}>
            <dt className={styles.label}>{term.label}</dt>
            <dd className={styles.value}>{term.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}
