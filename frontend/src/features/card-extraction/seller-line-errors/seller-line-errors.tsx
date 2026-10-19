import { type MessageKey, useTranslation } from "@/shared/i18n"
import { Icon } from "@/shared/ui"
import type { SellerLineIssue, SellerLineReason } from "../seller-lines"
import styles from "./seller-line-errors.module.css"

const REASON_KEY: Readonly<Record<SellerLineReason, MessageKey>> = {
  missing_separator: "stand:form.sellerErrors.missingSeparator",
  missing_name: "stand:form.sellerErrors.missingName",
  missing_value: "stand:form.sellerErrors.missingValue",
}

export interface SellerLineErrorsProps {
  readonly issues: readonly SellerLineIssue[]
}

export function SellerLineErrors({ issues }: SellerLineErrorsProps) {
  const { t } = useTranslation()
  return (
    <div className={styles.errors}>
      <p className={styles.summary}>
        <Icon name="alert" size="sm" />
        {t("stand:form.sellerErrors.summary")}
      </p>
      <ul className={styles.list}>
        {issues.map((issue) => (
          <li key={issue.line} className={styles.item}>
            <span>
              {t("stand:form.sellerErrors.line", {
                line: issue.line,
                reason: t(REASON_KEY[issue.reason]),
              })}
            </span>
            <code className={styles.source} dir="auto">
              {issue.text}
            </code>
          </li>
        ))}
      </ul>
    </div>
  )
}
