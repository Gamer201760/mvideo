import { clsx } from "clsx"
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react"
import { usePresence } from "../../../motion"
import { Icon } from "../../primitives/icon/icon"
import styles from "./select.module.css"

export interface SelectOption<T extends string> {
  readonly value: T
  readonly label: string
  readonly hint?: string
}

export interface SelectProps<T extends string> {
  readonly label: string
  readonly placeholder: string
  readonly options: readonly SelectOption<T>[]
  readonly value: T | null
  readonly onChange: (value: T) => void
  readonly className?: string | undefined
}

const STEP: Readonly<Record<string, number>> = { ArrowDown: 1, ArrowUp: -1 }

function nextIndex(key: string, current: number, total: number): number | null {
  if (key === "Home") return 0
  if (key === "End") return total - 1
  const step = STEP[key]
  if (step === undefined) return null
  return (current + step + total) % total
}

export function Select<T extends string>({
  label,
  placeholder,
  options,
  value,
  onChange,
  className,
}: SelectProps<T>) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const presence = usePresence(open, "--dur-exit")
  const selected = options.find((o) => o.value === value)

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", close)
    listRef.current?.focus()
    return () => document.removeEventListener("pointerdown", close)
  }, [open])

  useEffect(() => {
    if (!open) return
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" })
  }, [open, active])

  const show = () => {
    const index = options.findIndex((o) => o.value === value)
    setActive(index < 0 ? 0 : index)
    setOpen(true)
  }

  const choose = (index: number) => {
    const option = options[index]
    if (option !== undefined) onChange(option.value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const onListKey = (event: KeyboardEvent<HTMLElement>) => {
    const next = nextIndex(event.key, active, options.length)
    if (next !== null) {
      event.preventDefault()
      setActive(next)
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      choose(active)
    } else if (event.key === "Escape" || event.key === "Tab") {
      setOpen(false)
      triggerRef.current?.focus()
    }
  }

  const onTriggerKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault()
      show()
    }
  }

  return (
    <div ref={rootRef} className={clsx(styles.select, className)}>
      <span id={`${id}-label`} className={styles.label}>
        {label}
      </span>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={`${id}-label ${id}-value`}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onTriggerKey}
      >
        <span id={`${id}-value`} className={styles.value} data-placeholder={!selected}>
          {selected?.label ?? placeholder}
        </span>
        <Icon name="chevron-down" size="sm" className={styles.chevron} />
      </button>
      {presence.mounted ? (
        <div
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          aria-labelledby={`${id}-label`}
          aria-activedescendant={`${id}-option-${active}`}
          className={styles.list}
          data-state={presence.state}
          onAnimationEnd={presence.onAnimationEnd}
          onKeyDown={onListKey}
        >
          {options.map((option, index) => (
            <div
              key={option.value}
              id={`${id}-option-${index}`}
              role="option"
              tabIndex={-1}
              data-index={index}
              aria-selected={option.value === value}
              data-active={index === active}
              className={styles.option}
              onPointerMove={() => setActive(index)}
              onClick={() => choose(index)}
              onKeyDown={onListKey}
            >
              <span className={styles.optionLabel}>{option.label}</span>
              {option.hint === undefined ? null : (
                <span className={styles.hint}>{option.hint}</span>
              )}
              {option.value === value ? (
                <Icon name="check" size="sm" className={styles.check} />
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
