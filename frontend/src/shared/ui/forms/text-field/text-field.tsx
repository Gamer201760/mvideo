import { clsx } from "clsx"
import { type ChangeEvent, type KeyboardEventHandler, type ReactNode, type Ref, useId } from "react"
import styles from "./text-field.module.css"

export interface TextFieldProps {
  readonly label: string
  readonly value: string
  readonly onChange: (value: string) => void
  readonly placeholder?: string | undefined
  readonly hint?: string | undefined
  readonly rows?: number | undefined
  readonly required?: boolean | undefined
  readonly mono?: boolean | undefined
  readonly className?: string | undefined
  readonly error?: ReactNode
  readonly onBlur?: (() => void) | undefined
  readonly controlRef?: Ref<HTMLInputElement | HTMLTextAreaElement> | undefined
  readonly variant?: "default" | "inline"
  readonly disabled?: boolean | undefined
  readonly readOnly?: boolean | undefined
  readonly onKeyDown?: KeyboardEventHandler<HTMLInputElement | HTMLTextAreaElement> | undefined
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  rows,
  required = false,
  mono = false,
  className,
  error,
  onBlur,
  controlRef,
  variant = "default",
  disabled,
  readOnly,
  onKeyDown,
}: TextFieldProps) {
  const id = useId()
  const hintId = hint === undefined ? undefined : `${id}-hint`
  const errorId = error == null ? undefined : `${id}-error`
  const handle = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    onChange(event.target.value)
  const setControl = (element: HTMLInputElement | HTMLTextAreaElement | null) => {
    if (typeof controlRef === "function") return controlRef(element)
    if (controlRef != null) controlRef.current = element
  }
  const shared = {
    id,
    value,
    placeholder,
    required,
    disabled,
    readOnly,
    "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined,
    "aria-invalid": errorId === undefined ? undefined : true,
    className: clsx(styles.control, mono && styles.mono),
    onChange: handle,
    onBlur,
    onKeyDown,
    ref: setControl,
  }
  return (
    <div className={clsx(styles.field, variant === "inline" && styles.inline, className)}>
      <label htmlFor={id} className={clsx(styles.label, variant === "inline" && "visually-hidden")}>
        {label}
      </label>
      {rows === undefined ? (
        <input {...shared} type="text" />
      ) : (
        <textarea {...shared} rows={rows} />
      )}
      {hint === undefined ? null : (
        <span id={hintId} className={styles.hint}>
          {hint}
        </span>
      )}
      {errorId === undefined ? null : (
        <div id={errorId} className={styles.error} role="alert">
          {error}
        </div>
      )}
    </div>
  )
}
