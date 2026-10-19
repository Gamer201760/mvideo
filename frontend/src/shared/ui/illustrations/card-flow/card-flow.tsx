import styles from "./card-flow.module.css"

export interface CardFlowProps {
  readonly sourceTitle: string
  readonly resultTitle: string
}

export function CardFlow({ sourceTitle, resultTitle }: CardFlowProps) {
  return (
    <svg
      className={styles.scene}
      viewBox="0 0 600 400"
      aria-hidden="true"
      focusable="false"
      data-card-flow
    >
      <path className={styles.orbit} d="M8 330H590M84 12V388M518 12V388" />
      <circle className={styles.orbit} cx="300" cy="200" r="174" />
      <g className={styles.source}>
        <rect className={styles.paper} x="20" y="32" width="258" height="250" rx="16" />
        <path className={styles.rule} d="M40 88H258" />
        <text className={styles.heading} x="40" y="66">
          {sourceTitle}
        </text>
        <path
          className={styles.ink}
          d="M40 112H168M40 132H250M40 152H226M40 192H249M40 232H182M40 252H222"
        />
        <g className={styles.highlights}>
          <rect x="38" y="158" width="172" height="18" rx="4" />
          <rect x="112" y="198" width="140" height="18" rx="4" />
        </g>
        <path className={styles.evidenceInk} d="M44 168H204M118 208H246" />
      </g>
      <g className={styles.result}>
        <rect className={styles.paper} x="302" y="116" width="278" height="242" rx="16" />
        <text className={styles.heading} x="324" y="151">
          {resultTitle}
        </text>
        <path className={styles.rule} d="M324 170H558M324 226H558M324 282H558" />
        <path className={styles.mutedInk} d="M324 190H390M324 246H402M324 302H382" />
        <g className={styles.values}>
          <path className={styles.ink} d="M324 210H438M324 266H460M324 322H420" />
          <g className={styles.checks}>
            <path d="m534 207 5 5 10-12M534 263l5 5 10-12M534 319l5 5 10-12" />
          </g>
        </g>
      </g>
      <g className={styles.threads}>
        <path pathLength="1" d="M212 168C270 168 264 210 310 210" />
        <path pathLength="1" d="M254 208C292 208 270 266 310 266" />
        <path pathLength="1" d="M226 252C270 252 266 322 310 322" />
      </g>
      <g className={styles.knots}>
        <circle cx="310" cy="210" r="3" />
        <circle cx="310" cy="266" r="3" />
        <circle cx="310" cy="322" r="3" />
      </g>
    </svg>
  )
}
