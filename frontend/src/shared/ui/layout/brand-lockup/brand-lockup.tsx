import mvideoLogo from "../../brand-logos/mvideo.default.svg"
import styles from "./brand-lockup.module.css"
import { BrandMark } from "./brand-mark"

const DOTLESS_I = "ı"

export interface BrandLockupProps {
  readonly name: string
  readonly partnerPrefix: string
  readonly partnerName: string
}

function wordmarkParts(name: string): readonly [string, string] | null {
  const lower = name.toLowerCase()
  const at = lower.lastIndexOf("i")
  if (at < 0) return null
  return [lower.slice(0, at), lower.slice(at + 1)]
}

export function BrandLockup({ name, partnerPrefix, partnerName }: BrandLockupProps) {
  const parts = wordmarkParts(name)
  return (
    <span className={styles.lockup}>
      <BrandMark />
      <span className={styles.wordmark} aria-hidden="true">
        {parts === null ? (
          name.toLowerCase()
        ) : (
          <>
            {parts[0]}
            <span className={styles.knot}>{DOTLESS_I}</span>
            {parts[1]}
          </>
        )}
      </span>
      <span className={styles.partner}>
        <span className={styles.prefix}>{partnerPrefix}</span>
        <img className={styles.partnerLogo} src={mvideoLogo} alt={partnerName} />
      </span>
    </span>
  )
}
