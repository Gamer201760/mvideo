import { clsx } from "clsx"
import { useId } from "react"
import { useInputModality, useSlidingIndicator } from "../../../motion"
import { Icon, type IconName } from "../../primitives/icon/icon"
import styles from "./segmented.module.css"

export interface SegmentedOption<T extends string> {
  readonly value: T
  readonly label: string
  readonly icon?: IconName
  readonly short?: string
}

export type SegmentedDisplay = "label" | "icon" | "short"

export interface SegmentedProps<T extends string> {
  readonly label: string
  readonly options: readonly SegmentedOption<T>[]
  readonly value: T
  readonly onChange: (value: T) => void
  readonly display?: SegmentedDisplay
  readonly className?: string | undefined
}

interface OptionFaceProps {
  readonly label: string
  readonly icon: IconName | undefined
  readonly short: string | undefined
  readonly display: SegmentedDisplay
}

function OptionFace({ label, icon, short, display }: OptionFaceProps) {
  const glyph = icon === undefined ? null : <Icon name={icon} size="sm" />
  if (display === "label")
    return (
      <>
        {glyph}
        <span>{label}</span>
      </>
    )
  return (
    <>
      {display === "icon" ? glyph : <span aria-hidden="true">{short ?? label}</span>}
      <span className="visually-hidden">{label}</span>
    </>
  )
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  display = "label",
  className,
}: SegmentedProps<T>) {
  const name = useId()
  const modality = useInputModality()
  const { listRef, indicatorRef, itemRef } = useSlidingIndicator<HTMLFieldSetElement>(value, {
    instant: modality.instant,
    radiusToken: "--radius-md",
  })
  return (
    <fieldset
      ref={listRef}
      className={clsx(styles.segmented, className)}
      onKeyDown={modality.onKeyDown}
      onPointerDown={modality.onPointerDown}
    >
      <legend className="visually-hidden">{label}</legend>
      <span ref={indicatorRef} className={styles.indicator} aria-hidden="true" />
      {options.map((option) => (
        <label
          key={option.value}
          ref={itemRef(option.value)}
          className={styles.option}
          data-checked={option.value === value}
          title={display === "label" ? undefined : option.label}
        >
          <input
            className={styles.input}
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          <OptionFace
            label={option.label}
            icon={option.icon}
            short={option.short}
            display={display}
          />
        </label>
      ))}
    </fieldset>
  )
}
