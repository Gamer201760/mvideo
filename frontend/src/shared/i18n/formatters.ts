import { INTL_LOCALE, type Locale } from "./locale"

export type DateInput = Date | string | number

export interface Formatters {
  readonly number: (value: number, fractionDigits?: number) => string
  readonly integer: (value: number) => string
  readonly percent: (ratio: number, fractionDigits?: number) => string
  readonly money: (value: number, currency: string) => string
  readonly date: (value: DateInput) => string
  readonly time: (value: DateInput) => string
  readonly dateTime: (value: DateInput) => string
  readonly relative: (value: number, unit: Intl.RelativeTimeFormatUnit) => string
  readonly list: (items: readonly string[]) => string
}

function digits(fractionDigits: number): Intl.NumberFormatOptions {
  return { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits }
}

function numberFormatCache(tag: string): (options: Intl.NumberFormatOptions) => Intl.NumberFormat {
  const cache = new Map<string, Intl.NumberFormat>()
  return (options) => {
    const key = JSON.stringify(options)
    const cached = cache.get(key)
    if (cached !== undefined) return cached
    const format = new Intl.NumberFormat(tag, options)
    cache.set(key, format)
    return format
  }
}

export function createFormatters(locale: Locale, timeZone?: string): Formatters {
  const tag = INTL_LOCALE[locale]
  const zone = timeZone === undefined ? {} : { timeZone }
  const numberFormat = numberFormatCache(tag)
  const dateFormat = new Intl.DateTimeFormat(tag, { dateStyle: "long", ...zone })
  const timeFormat = new Intl.DateTimeFormat(tag, { timeStyle: "short", ...zone })
  const dateTimeFormat = new Intl.DateTimeFormat(tag, {
    dateStyle: "medium",
    timeStyle: "short",
    ...zone,
  })
  const relativeFormat = new Intl.RelativeTimeFormat(tag, { numeric: "auto" })
  const listFormat = new Intl.ListFormat(tag, { style: "long", type: "conjunction" })

  return {
    number: (value, fractionDigits = 1) => numberFormat(digits(fractionDigits)).format(value),
    integer: (value) => numberFormat({ maximumFractionDigits: 0 }).format(value),
    percent: (ratio, fractionDigits = 0) =>
      numberFormat({ style: "percent", ...digits(fractionDigits) }).format(ratio),
    money: (value, currency) => numberFormat({ style: "currency", currency }).format(value),
    date: (value) => dateFormat.format(new Date(value)),
    time: (value) => timeFormat.format(new Date(value)),
    dateTime: (value) => dateTimeFormat.format(new Date(value)),
    relative: (value, unit) => relativeFormat.format(value, unit),
    list: (items) => listFormat.format(items),
  }
}
