import { clsx } from "clsx"
import type { HTMLAttributes, Ref } from "react"
import styles from "./scroll-area.module.css"

export interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
  readonly ref?: Ref<HTMLDivElement> | undefined
}

export function ScrollArea({ className, ...props }: ScrollAreaProps) {
  return <div {...props} className={clsx(styles.area, className)} />
}
