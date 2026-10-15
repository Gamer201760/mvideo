import { clsx } from "clsx"
import type { ButtonHTMLAttributes, MouseEvent, ReactNode, Ref } from "react"
import { Icon, type IconName } from "../icon/icon"
import styles from "./button.module.css"

export type ButtonVariant = "primary" | "secondary" | "ghost"
export type ButtonSize = "regular" | "compact"

export const VARIANT_CLASS: Readonly<Record<ButtonVariant, string | undefined>> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
}

export const SIZE_CLASS: Readonly<Record<ButtonSize, string | undefined>> = {
  regular: undefined,
  compact: styles.compact,
}

export interface ButtonContentProps {
  readonly icon?: IconName | undefined
  readonly pending?: boolean
  readonly children: ReactNode
}

export function ButtonContent({ icon, pending = false, children }: ButtonContentProps) {
  return (
    <>
      <span className={styles.content} data-pending={pending}>
        {icon === undefined ? null : <Icon name={icon} size="sm" />}
        <span>{children}</span>
      </span>
      {pending ? <Icon name="loader" size="sm" className={styles.loader} /> : null}
    </>
  )
}

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "type"> {
  readonly variant?: ButtonVariant
  readonly size?: ButtonSize
  readonly icon?: IconName | undefined
  readonly pending?: boolean
  readonly type?: "button" | "submit"
  readonly ref?: Ref<HTMLButtonElement> | undefined
  readonly children: ReactNode
}

export function Button({
  variant = "primary",
  size = "regular",
  icon,
  pending = false,
  type = "button",
  className,
  onClick,
  children,
  ...rest
}: ButtonProps) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (pending) {
      event.preventDefault()
      return
    }
    onClick?.(event)
  }
  return (
    <button
      {...rest}
      type={type}
      className={clsx(styles.button, VARIANT_CLASS[variant], SIZE_CLASS[size], className)}
      aria-busy={pending || undefined}
      aria-disabled={pending || undefined}
      onClick={handleClick}
    >
      <ButtonContent icon={icon} pending={pending}>
        {children}
      </ButtonContent>
    </button>
  )
}
