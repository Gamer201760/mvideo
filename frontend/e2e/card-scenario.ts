import { type APIRequestContext, type BrowserContext, expect, type Page } from "@playwright/test"
import type { components } from "../src/shared/api/schema.gen"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import fixture from "./fixtures/jury-route.json" with { type: "json" }

type Schemas = components["schemas"]
type ExtractResult = Schemas["ExtractResponse"]
type Example = Schemas["ExampleSchema"]

export async function example(request: APIRequestContext): Promise<Example> {
  const response = await request.get("/api/v1/examples")
  expect(response.ok(), await response.text()).toBe(true)
  const result: Schemas["ExamplesResponse"] = await response.json()
  const card = result.items.find((item) => item.category_id === fixture.categoryId)
  if (card === undefined) throw new Error("Synthetic smartphone example is missing")
  return card
}

export async function fillCard(page: Page, title: string, description: string): Promise<void> {
  await page.goto("/")
  const newCard = page.getByRole("button", { name: copy.form.back, exact: true })
  await expect(
    page.getByRole("textbox", { name: copy.form.titleField, exact: true }).or(newCard),
  ).toBeVisible()
  if (await newCard.isVisible()) await newCard.click()
  await page.getByRole("textbox", { name: copy.form.titleField, exact: true }).fill(title)
  await page
    .getByRole("textbox", { name: copy.form.descriptionField, exact: true })
    .fill(description)
}

export async function submitCard(page: Page): Promise<ExtractResult> {
  const response = page.waitForResponse(
    (candidate) =>
      candidate.url().endsWith("/api/v1/extract") && candidate.request().method() === "POST",
  )
  await page.getByRole("button", { name: copy.form.submit, exact: true }).click()
  const received = await response
  expect(received.ok(), await received.text()).toBe(true)
  const result: ExtractResult = await received.json()
  await expect(page.getByRole("heading", { name: copy.result.title })).toBeVisible()
  return result
}

export function attributeRow(page: Page, attribute: string) {
  return page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: attribute, exact: true }),
  })
}

export async function prepareStand({
  context,
  request,
}: {
  context: BrowserContext
  request: APIRequestContext
}) {
  const response = await request.get("/api/v1/ready")
  expect(response.ok(), "Scenario tests require a ready local backend").toBe(true)
  expect(await response.json()).toMatchObject({
    ready: true,
    mode: "local_rules",
    model: null,
    synthetic: true,
  })
  await context.addInitScript(() => {
    localStorage.setItem("app-locale", "ru")
    localStorage.setItem("app-theme", "light")
  })
}
