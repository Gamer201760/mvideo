import type { ReviewAction, ReviewItem } from "@/entities/stand"
import { ReviewRow } from "../review-row/review-row"
import styles from "./review-items.module.css"

export interface ReviewItemsProps {
  readonly items: readonly ReviewItem[]
  readonly pendingId: string | undefined
  readonly onAct: (id: string, action: ReviewAction, value?: string) => void
}

export function ReviewItems({ items, pendingId, onAct }: ReviewItemsProps) {
  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <ReviewRow
          key={item.id}
          item={item}
          pending={pendingId === item.id}
          disabled={pendingId !== undefined}
          onAccept={() => onAct(item.id, "accept")}
          onCorrect={(value) => onAct(item.id, "correct", value)}
        />
      ))}
    </ul>
  )
}
