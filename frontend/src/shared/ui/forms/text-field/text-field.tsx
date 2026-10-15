import { clsx } from "clsx"
import { type ChangeEvent, useId } from "react"
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
}: TextFieldProps) {
  const id = useId()
  const hintId = hint === undefined ? undefined : `${id}-hint`
  const handle = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    onChange(event.target.value)
  const shared = {
    id,
    value,
    placeholder,
    required,
    "aria-describedby": hintId,
    className: clsx(styles.control, mono && styles.mono),
    onChange: handle,
  }
  return (
    <div className={clsx(styles.field, className)}>
      <label htmlFor={id} className={styles.label}>
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
    </div>
  )
}
