import { clsx } from "clsx"
import { type HTMLAttributes, type ReactNode, useId } from "react"
import { staggerStyle } from "../../../motion"
import styles from "./card.module.css"

export interface CardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  readonly as?: "section" | "article" | "aside" | "div"
  readonly title?: ReactNode
  readonly eyebrow?: ReactNode
  readonly description?: ReactNode
  readonly actions?: ReactNode
  readonly motionIndex?: number | undefined
  readonly children: ReactNode
}

interface CardHeaderProps {
  readonly titleId: string
  readonly title: ReactNode
  readonly eyebrow: ReactNode
  readonly description: ReactNode
  readonly actions: ReactNode
}

function CardHeader({ titleId, title, eyebrow, description, actions }: CardHeaderProps) {
  return (
    <header className={styles.header}>
      <hgroup className={styles.heading}>
        {eyebrow === undefined ? null : <p className={styles.eyebrow}>{eyebrow}</p>}
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        {description === undefined ? null : <p className={styles.description}>{description}</p>}
      </hgroup>
      {actions === undefined ? null : <div className={styles.actions}>{actions}</div>}
    </header>
  )
}

export function Card({
  as: Tag = "section",
  title,
  eyebrow,
  description,
  actions,
  motionIndex,
  className,
  style,
  children,
  ...rest
}: CardProps) {
  const titleId = useId()
  const titled = title !== undefined
  const entering = motionIndex !== undefined
  return (
    <Tag
      aria-labelledby={titled && rest["aria-label"] === undefined ? titleId : undefined}
      {...rest}
      className={clsx(styles.card, entering && styles.entering, className)}
      style={entering ? { ...style, ...staggerStyle(motionIndex) } : style}
      data-motion={entering ? "fade" : undefined}
    >
      {titled ? (
        <CardHeader
          titleId={titleId}
          title={title}
          eyebrow={eyebrow}
          description={description}
          actions={actions}
        />
      ) : null}
      {children}
    </Tag>
  )
}
