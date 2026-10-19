import type { ExtractedValue, ExtractResult, ReviewItem } from "./stand.queries"

function reviewedValue(
  item: ReviewItem,
  text: string,
  value?: ExtractedValue,
): ExtractedValue | undefined {
  const start = text.indexOf(item.evidence)
  if (item.resolved_value === null || start < 0 || item.evidence === "") return value
  if (
    value?.source === "review" &&
    value.evidence === item.evidence &&
    value.value === item.resolved_value
  )
    return value
  return {
    attribute: item.attribute,
    value: item.resolved_value,
    evidence: item.evidence,
    start,
    end: start + item.evidence.length,
    status: "accepted",
    review_id: item.id,
    source: "review",
    acceptance: "manual",
    sources: ["review", ...(value?.sources ?? []).filter((source) => source !== "review")],
    confidence: item.resolved_value === value?.value ? value.confidence : null,
    risk: item.resolved_value === value?.value ? (value.risk ?? null) : null,
  }
}

export function reconcileReviews(
  result: ExtractResult,
  items: readonly ReviewItem[],
): ExtractResult {
  const decisions = latestDecisions(items)
  const apply = (values: readonly ExtractedValue[]) =>
    values
      .filter((value) => decisions.get(value.attribute)?.status !== "rejected")
      .map((value) => {
        const item = decisions.get(value.attribute)
        return item === undefined ? value : (reviewedValue(item, result.text, value) ?? value)
      })
  const values = apply(result.values)
  const extra = apply(result.extra_values ?? [])
  const found = new Set([...values, ...extra].map((value) => value.attribute))
  const attributes = new Set([...(result.category?.attributes ?? []), ...result.missing])
  const removed = [...result.values, ...(result.extra_values ?? [])]
    .filter((value) => decisions.get(value.attribute)?.status === "rejected")
    .map((value) => value.attribute)
  for (const item of decisions.values()) {
    if (item.status === "rejected") continue
    if (found.has(item.attribute)) continue
    const value = reviewedValue(item, result.text)
    if (value === undefined) continue
    const target = attributes.has(item.attribute) ? values : extra
    target.push(value)
    found.add(item.attribute)
  }
  return {
    ...result,
    values,
    extra_values: extra,
    ...(result.rejections === undefined
      ? {}
      : { rejections: result.rejections.filter((rejection) => !found.has(rejection.attribute)) }),
    missing: [...new Set([...result.missing, ...removed.filter((a) => attributes.has(a))])].filter(
      (attribute) => !found.has(attribute),
    ),
  }
}

export function latestDecisions(items: readonly ReviewItem[]): Map<string, ReviewItem> {
  const decisions = new Map<string, ReviewItem>()
  for (const item of items) {
    if (item.status === "pending" || item.status === "auto_accepted") continue
    const previous = decisions.get(item.attribute)
    if (previous === undefined || (previous.resolved_at ?? "") < (item.resolved_at ?? "")) {
      decisions.set(item.attribute, item)
    }
  }
  return decisions
}
