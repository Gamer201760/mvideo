import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CardSources } from "@/features/card-extraction/card-sources/card-sources"
import { api } from "@/shared/api"
import { createI18n, LocaleProvider } from "@/shared/i18n"
import { setReducedMotion } from "../../setup/motionEnvironment"

afterEach(() => vi.restoreAllMocks())

describe("manual card entry without examples", () => {
  it.each(["ru", "en"] as const)(
    "keeps the form usable in %s when examples fail and retries them",
    async (locale) => {
      setReducedMotion(true)
      let attempts = 0
      vi.spyOn(api, "GET").mockImplementation(async (path: string) => {
        if (path === "/api/v1/stand") {
          return {
            data: { categories: [], built_at: "2026-10-19", threshold: 0.95 } as never,
            response: new Response(),
          }
        }
        attempts += 1
        return attempts === 1
          ? {
              error: { code: "storage_unavailable", message: "Unavailable" },
              response: new Response(null, { status: 503 }),
            }
          : { data: { items: [] } as never, response: new Response() }
      })
      const instance = createI18n(locale)
      const t = instance.t.bind(instance)
      const submit = vi.fn()
      render(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <LocaleProvider instance={instance}>
            <CardSources pending={false} onSubmit={submit} />
          </LocaleProvider>
        </QueryClientProvider>,
      )
      const user = userEvent.setup()
      const title = await screen.findByRole("textbox", { name: t("stand:form.titleField") })
      await screen.findByText(t("errors:api.storage_unavailable"))
      await user.type(title, "Manual card")
      await user.click(screen.getByRole("button", { name: t("stand:form.submit") }))
      expect(submit).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({ title: "Manual card" }),
      )
      await user.click(screen.getByRole("button", { name: t("common:action.retry") }))
      await screen.findByRole("textbox", { name: t("stand:form.titleField") })
      expect((title as HTMLInputElement).value).toBe("Manual card")
      expect(attempts).toBe(2)
    },
  )
})
