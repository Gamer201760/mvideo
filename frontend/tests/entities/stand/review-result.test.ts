import { describe, expect, it } from "vitest"
import { reconcileReviews } from "@/entities/stand/review-result"
import type { ExtractResult, ReviewItem } from "@/entities/stand/stand.queries"

const snapshot: ExtractResult = {
  engine: "hybrid",
  text: "Color: blue\nWeight: 2 kg",
  threshold: null,
  auto_accept_enabled: false,
  category: { category_id: 1, name: "Test", path: "Test", attributes: ["Color", "Weight"] },
  missing: ["Weight"],
  values: [
    {
      attribute: "Color",
      value: "blue",
      evidence: "Color: blue",
      start: 0,
      end: 11,
      confidence: 0.5,
      source: "hybrid",
      sources: ["hybrid"],
      status: "review",
      review_id: "color",
    },
  ],
}

function decision(changes: Partial<ReviewItem> = {}): ReviewItem {
  return {
    id: "color",
    category_id: 1,
    title: "Card",
    attribute: "Color",
    value: "blue",
    evidence: "Color: blue",
    confidence: 0.5,
    source: "hybrid",
    status: "corrected",
    resolved_value: "navy",
    created_at: "2026-10-19T08:00:00Z",
    resolved_at: "2026-10-19T08:01:00Z",
    ...changes,
  }
}

describe("reconcileReviews", () => {
  it("keeps automatic acceptance separate from a human decision", () => {
    const original = snapshot.values[0]
    if (original === undefined) throw new Error("Missing extracted field")
    const result = {
      ...snapshot,
      auto_accept_enabled: true,
      values: [{ ...original, status: "accepted" as const, acceptance: "automatic" as const }],
    }
    const reconciled = reconcileReviews(result, [
      decision({ status: "auto_accepted", resolved_value: null, resolved_at: null }),
    ])
    expect(reconciled.values[0]).toMatchObject({
      value: "blue",
      acceptance: "automatic",
      source: "hybrid",
    })
  })
  it("preserves the value and full support score on confirmation", () => {
    const original = snapshot.values[0]
    if (original === undefined) throw new Error("Missing extracted field")
    const full = {
      ...snapshot,
      values: [
        {
          ...original,
          confidence: 1,
          risk: {
            score: 1,
            level: "low" as const,
            reasons: ["exact_quote"],
            method: "heuristic" as const,
          },
        },
      ],
    }
    const updated = reconcileReviews(full, [
      decision({ status: "accepted", resolved_value: "blue" }),
    ])
    expect(updated.values[0]).toMatchObject({
      value: "blue",
      confidence: 1,
      risk: { score: 1 },
      status: "accepted",
    })
  })
  it("replaces a stale value with the latest server decision", () => {
    const updated = reconcileReviews(snapshot, [
      decision({ resolved_value: "cyan", resolved_at: "2026-10-19T08:02:00Z" }),
      decision(),
    ])
    expect(updated.values[0]).toMatchObject({
      value: "cyan",
      source: "review",
      status: "accepted",
      review_id: "color",
      risk: null,
      confidence: null,
    })
    expect(snapshot.values[0]?.value).toBe("blue")
  })

  it("replaces a previously confirmed snapshot after a manual override", () => {
    const original = snapshot.values[0]
    if (original === undefined) throw new Error("Missing extracted field")
    const previous = {
      ...snapshot,
      values: [{ ...original, source: "review", status: "accepted" as const }],
    }
    const updated = reconcileReviews(previous, [decision({ resolved_value: "cyan" })])
    expect(updated.values[0]).toMatchObject({ value: "cyan", source: "review", status: "accepted" })
  })

  it("restores a required field confirmed after the snapshot was saved", () => {
    const updated = reconcileReviews(snapshot, [
      decision({
        id: "weight",
        attribute: "Weight",
        value: "2 kg",
        evidence: "Weight: 2 kg",
        resolved_value: "2 kg",
      }),
    ])
    expect(updated.missing).toEqual([])
    expect(updated.values.find((value) => value.attribute === "Weight")).toMatchObject({
      value: "2 kg",
      source: "review",
      status: "accepted",
      start: 12,
      end: 24,
    })
  })

  it("keeps the snapshot when a decision has no quote in the card", () => {
    const updated = reconcileReviews(snapshot, [decision({ evidence: "Another card" })])
    expect(updated.values).toEqual(snapshot.values)
  })

  it("removes a stale rejection after a missing field is confirmed", () => {
    const rejected = {
      ...snapshot,
      rejections: [
        { attribute: "Weight", reason: "field_unconfirmed", evidence: "Weight: 2 kg" },
        { attribute: "Material", reason: "value_unconfirmed", evidence: "Unknown" },
      ],
    }
    const updated = reconcileReviews(rejected, [
      decision({ attribute: "Weight", evidence: "Weight: 2 kg", resolved_value: "2 kg" }),
    ])
    expect(updated.missing).toEqual([])
    expect(updated.rejections).toEqual([rejected.rejections[1]])
    expect(rejected.rejections).toHaveLength(2)
  })

  it("removes rejected values and restores required fields to the missing list", () => {
    const rejected = decision({ status: "rejected", resolved_value: null })
    const updated = reconcileReviews(snapshot, [rejected])
    expect(updated.values).toEqual([])
    expect(updated.missing).toEqual(["Weight", "Color"])
    expect(snapshot.values).toHaveLength(1)
  })

  it("uses the latest decision when a rejected field was added back", () => {
    const updated = reconcileReviews(snapshot, [
      decision({ status: "rejected", resolved_value: null }),
      decision({ id: "new-color", resolved_value: "blue", resolved_at: "2026-10-19T08:02:00Z" }),
    ])
    expect(updated.values[0]).toMatchObject({
      value: "blue",
      review_id: "new-color",
      acceptance: "manual",
    })
    expect(updated.missing).toEqual(["Weight"])
  })
})
