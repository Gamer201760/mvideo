import type { ReactNode } from "react"
import type { ExtractedValue } from "../stand.queries"
import styles from "./card-text.module.css"

export interface CardTextProps {
  readonly text: string
  readonly values: readonly ExtractedValue[]
  readonly activeAttribute: string | null
}

interface Span {
  readonly start: number
  readonly end: number
  readonly value: ExtractedValue
}

function spansOf(values: readonly ExtractedValue[], length: number, active: string | null): Span[] {
  const selected = values.find(
    (value) =>
      value.attribute === active &&
      value.start >= 0 &&
      value.end > value.start &&
      value.end <= length,
  )
  const sorted = values
    .filter((v) => v.end > v.start && v.start >= 0 && v.end <= length)
    .filter(
      (value) =>
        selected === undefined ||
        value === selected ||
        value.end <= selected.start ||
        value.start >= selected.end,
    )
    .map((value) => ({ start: value.start, end: value.end, value }))
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const kept: Span[] = []
  for (const span of sorted) {
    const last = kept.at(-1)
    if (last === undefined || span.start >= last.end) kept.push(span)
  }
  return kept
}

export function CardText({ text, values, activeAttribute }: CardTextProps) {
  const parts: ReactNode[] = []
  let cursor = 0
  for (const span of spansOf(values, text.length, activeAttribute)) {
    if (span.start > cursor) parts.push(text.slice(cursor, span.start))
    parts.push(
      <mark
        key={`${span.value.attribute}-${span.start}`}
        className={styles.mark}
        data-status={span.value.status}
        data-active={span.value.attribute === activeAttribute}
        data-thread-target={span.value.attribute}
        title={span.value.attribute}
      >
        {text.slice(span.start, span.end)}
      </mark>,
    )
    cursor = span.end
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return (
    <p className={styles.text} lang="ru">
      {parts}
    </p>
  )
}
