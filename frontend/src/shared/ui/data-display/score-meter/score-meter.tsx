import { clsx } from "clsx"
import type { CSSProperties } from "react"
import styles from "./score-meter.module.css"

export type ScoreTone = "settled" | "attention"

const TONE_CLASS: Readonly<Record<ScoreTone, string | undefined>> = {
  settled: styles.settled,
  attention: styles.attention,
}

export interface ScoreMeterProps {
  readonly value: number
  readonly tone: ScoreTone
  readonly label: string
  readonly className?: string | undefined
}

export function ScoreMeter({ value, tone, label, className }: ScoreMeterProps) {
  const share = Math.min(1, Math.max(0, value))
  return (
    <span className={clsx(styles.meter, TONE_CLASS[tone], className)} role="img" aria-label={label}>
      <span className={styles.fill} style={{ "--share": share } as CSSProperties} />
    </span>
  )
}
