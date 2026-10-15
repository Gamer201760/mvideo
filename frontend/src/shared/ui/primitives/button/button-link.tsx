import { clsx } from "clsx"
import type { ReactNode } from "react"
import { Link, type To } from "react-router"
import type { IconName } from "../icon/icon"
import {
  ButtonContent,
  type ButtonSize,
  type ButtonVariant,
  SIZE_CLASS,
  VARIANT_CLASS,
} from "./button"
import styles from "./button.module.css"

export interface ButtonLinkProps {
  readonly to: To
  readonly variant?: ButtonVariant
  readonly size?: ButtonSize
  readonly icon?: IconName | undefined
  readonly className?: string | undefined
  readonly children: ReactNode
}

export function ButtonLink({
  to,
  variant = "primary",
  size = "regular",
  icon,
  className,
  children,
}: ButtonLinkProps) {
  return (
    <Link
      to={to}
      viewTransition
      className={clsx(styles.button, VARIANT_CLASS[variant], SIZE_CLASS[size], className)}
    >
      <ButtonContent icon={icon}>{children}</ButtonContent>
    </Link>
  )
}
