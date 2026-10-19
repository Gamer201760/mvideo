import { clsx } from "clsx"
import { Icon } from "@/shared/ui"
import styles from "./category-path.module.css"

export interface CategoryPathProps {
  readonly path: string
  readonly className?: string | undefined
}

export function CategoryPath({ path, className }: CategoryPathProps) {
  const parts = path
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part !== "")
  const leaf = parts.at(-1) ?? path
  return (
    <span className={clsx(styles.path, className)} lang="ru">
      <span className="visually-hidden">{path}</span>
      <span className={styles.visual} aria-hidden="true">
        {parts.slice(0, -1).map((part, index) => (
          <span key={parts.slice(0, index + 1).join("/")} className={styles.parent}>
            {part}
            <Icon name="chevron-right" size="sm" className={styles.separator} />
          </span>
        ))}
        <span className={styles.leaf}>{leaf}</span>
      </span>
    </span>
  )
}
