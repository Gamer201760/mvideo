import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  type ExtractResult,
  type ReviewItem,
  reconcileReviews,
  useCardReviews,
} from "@/entities/stand"
import { CardCompletion } from "@/features/card-extraction/card-completion/card-completion"
import { ExtractionResult } from "@/features/card-extraction/extraction-result/extraction-result"
import { useInlineReview } from "@/features/card-extraction/inline-review/use-inline-review"
import { api } from "@/shared/api"
import { createI18n, LocaleProvider } from "@/shared/i18n"
import { setReducedMotion } from "../../../setup/motionEnvironment"

const input = {
  engine: "hybrid" as const,
  title: "Card",
  description: "Color: blue",
  category_id: 1,
}
const snapshot: ExtractResult = {
  engine: "hybrid",
  text: "Color: blue",
  threshold: 0.95,
  auto_accept_enabled: true,
  category: { category_id: 1, name: "Card", path: "Card", attributes: ["Color"] },
  missing: [],
  values: [
    {
      attribute: "Color",
      value: "blue",
      evidence: "Color: blue",
      start: 0,
      end: 11,
      confidence: 1,
      source: "hybrid",
      sources: ["hybrid"],
      status: "review",
      review_id: "color",
    },
  ],
}

function Workspace({ original }: { readonly original: ExtractResult }) {
  const reviews = useCardReviews(input)
  const result = reconcileReviews(original, reviews.data?.items ?? [])
  const slots = useInlineReview(reviews.data, reviews.isFetching)
  return (
    <>
      <ExtractionResult
        result={result}
        pending={false}
        error={null}
        onRetry={vi.fn()}
        reviewSlots={slots}
      />
      <CardCompletion
        input={input}
        result={result}
        reviews={reviews.data}
        disabled={reviews.isFetching}
      />
    </>
  )
}

function setup(status: ReviewItem["status"], fail = false) {
  setReducedMotion(true)
  let current: ReviewItem = {
    id: "color",
    category_id: 1,
    title: "Card",
    attribute: "Color",
    value: "blue",
    evidence: "Color: blue",
    confidence: 1,
    source: "hybrid",
    status,
    resolved_value: status === "corrected" ? "navy" : null,
    created_at: "2026-10-19T08:00:00Z",
    resolved_at: status === "corrected" ? "2026-10-19T08:00:00Z" : null,
  }
  let failure = fail
  const requests: unknown[] = []
  vi.spyOn(api, "GET").mockResolvedValue({ data: {} as never, response: new Response() })
  vi.spyOn(api, "POST").mockImplementation(
    async (path: string, options?: { readonly body?: unknown }) => {
      if (path === "/api/v1/review/card") {
        return {
          data: {
            card_key: "card",
            items:
              status === "corrected"
                ? [
                    {
                      ...current,
                      id: "older",
                      status: "corrected",
                      resolved_value: "stale",
                      resolved_at: "2026-10-18T08:00:00Z",
                    },
                    current,
                  ]
                : [current],
          } as never,
          response: new Response(),
        }
      }
      requests.push(options?.body)
      if (failure) {
        failure = false
        return {
          error: { code: "storage_busy", message: "Busy" },
          response: new Response(null, { status: 503 }),
        }
      }
      const action =
        options?.body !== undefined &&
        options.body !== null &&
        typeof options.body === "object" &&
        "action" in options.body
          ? options.body.action
          : null
      current =
        action === "reject"
          ? {
              ...current,
              status: "rejected",
              resolved_value: null,
              resolved_at: "2026-10-19T08:01:00Z",
            }
          : {
              ...current,
              status: "corrected",
              resolved_value: current.value,
              resolved_at: "2026-10-19T08:02:00Z",
            }
      return { data: current as never, response: new Response() }
    },
  )
  const value = snapshot.values[0]
  if (value === undefined) throw new Error("Missing value")
  const original =
    status === "auto_accepted"
      ? {
          ...snapshot,
          values: [{ ...value, status: "accepted" as const, acceptance: "automatic" as const }],
        }
      : snapshot
  const instance = createI18n("en")
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const show = () =>
    render(
      <QueryClientProvider client={client}>
        <LocaleProvider instance={instance}>
          <Workspace original={original} />
        </LocaleProvider>
      </QueryClientProvider>,
    )
  const view = show()
  return { requests, user: userEvent.setup(), t: instance.t.bind(instance), client, show, view }
}

afterEach(() => vi.restoreAllMocks())

describe("reject values from the result table", () => {
  it.each(["pending", "auto_accepted", "corrected"] as const)(
    "rejects %s through the real mutation, reconciles and restores the saved decision",
    async (status) => {
      const { user, t, requests, client, show, view } = setup(status)
      const reject = await screen.findByRole("button", {
        name: t("stand:review.rejectInline", { attribute: "Color" }),
      })
      await waitFor(() => expect(reject.hasAttribute("disabled")).toBe(false))
      await user.click(reject)
      await screen.findByRole("region", { name: t("stand:review.rejectedTitle") })
      expect(
        screen.queryByRole("textbox", {
          name: t("stand:review.editInline", { attribute: "Color" }),
        }),
      ).toBeNull()
      expect(
        screen.getByRole("button", { name: t("stand:review.addInline", { attribute: "Color" }) }),
      ).toBeTruthy()
      expect(requests[0]).toEqual(
        status === "corrected"
          ? { action: "reject", override: true, expected_value: "navy" }
          : { action: "reject", override: false },
      )
      expect(document.activeElement).toBe(document.querySelector("[data-review-summary]"))
      view.unmount()
      client.clear()
      show()
      await screen.findByRole("region", { name: t("stand:review.rejectedTitle") })
      const restore = screen.getByRole("button", {
        name: t("stand:review.restoreInline", { attribute: "Color" }),
      })
      await waitFor(() => expect(restore.hasAttribute("disabled")).toBe(false))
      await user.click(restore)
      await screen.findByRole("textbox", {
        name: t("stand:review.editInline", { attribute: "Color" }),
      })
      expect(screen.queryByRole("region", { name: t("stand:review.rejectedTitle") })).toBeNull()
    },
  )

  it("keeps the value on storage failure and allows retry through the same button", async () => {
    const { user, t, requests } = setup("corrected", true)
    const reject = await screen.findByRole("button", {
      name: t("stand:review.rejectInline", { attribute: "Color" }),
    })
    await waitFor(() => expect(reject.hasAttribute("disabled")).toBe(false))
    await user.click(reject)
    expect((await screen.findByRole("alert")).textContent).toContain(t("errors:api.storage_busy"))
    expect(
      screen.getByRole("textbox", { name: t("stand:review.editInline", { attribute: "Color" }) }),
    ).toBeTruthy()
    await user.click(reject)
    await screen.findByRole("region", { name: t("stand:review.rejectedTitle") })
    expect(requests).toHaveLength(2)
  })
})
