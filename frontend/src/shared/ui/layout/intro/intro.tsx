import type { ReactNode } from "react"
import styles from "./intro.module.css"

export interface IntroProps {
  readonly title: string
  readonly description: string
  readonly children?: ReactNode
}

export function Intro({ title, description, children }: IntroProps) {
  return (
    <div className={styles.intro}>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.description}>{description}</p>
      {children}
    </div>
  )
}
