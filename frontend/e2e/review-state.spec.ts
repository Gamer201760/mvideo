import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"

test.beforeEach(prepareStand)

test("reconcile a saved result with a decision from another tab without extraction", async ({
  page,
  context,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} reconcile ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((item) => item.review_id !== null)
  if (value?.review_id == null) throw new Error("A pending value is required")
  const other = await context.newPage()
  await other.goto("/")
  const corrected = `${value.value} verified`
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  const row = attributeRow(other, value.attribute)
  await row
    .getByRole("textbox", {
      name: copy.review.editInline.replace("{{attribute}}", value.attribute),
      exact: true,
    })
    .click()
  await row.getByRole("textbox").fill(corrected)
  await row.getByRole("textbox").press("Enter")
  await page.bringToFront()
  await expect(attributeRow(page, value.attribute).getByRole("textbox")).toHaveValue(corrected)
  await expect(attributeRow(other, value.attribute).getByRole("textbox")).toHaveValue(corrected)
  expect(extractions).toBe(0)
})

test("check a stale snapshot against the server on reload", async ({ page, request }) => {
  const card = await example(request)
  await fillCard(page, `${card.title} snapshot ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((item) => item.review_id !== null)
  if (value?.review_id == null) throw new Error("A pending value is required")
  const corrected = `${value.value} checked`
  const response = await request.post(`/api/v1/review/${value.review_id}`, {
    data: { action: "correct", value: corrected },
  })
  expect(response.ok()).toBe(true)
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  await page.reload()
  await expect(attributeRow(page, value.attribute).getByRole("textbox")).toHaveValue(corrected)
  expect(extractions).toBe(0)
})

test("restore an interrupted request and retain the previous completed result", async ({
  page,
  request,
}) => {
  const card = await example(request)
  const first = `${card.title} completed ${Date.now()}`
  await fillCard(page, first, card.description)
  await submitCard(page)
  const second = `${card.title} interrupted ${Date.now()}`
  await fillCard(page, second, card.description)
  await page.route("**/api/v1/extract", (route) => route.abort("connectionreset"))
  const failed = page.waitForEvent("requestfailed", {
    predicate: (request) => request.url().endsWith("/api/v1/extract"),
  })
  await page.getByRole("button", { name: copy.form.submit, exact: true }).click()
  await failed
  await page.reload()
  await expect(page.getByRole("heading", { name: copy.workspace.interrupted })).toBeVisible()
  await expect(page.getByText(second, { exact: true })).toBeVisible()
  await page.getByRole("button", { name: copy.workspace.previous, exact: true }).click()
  await expect(page.getByRole("heading", { name: copy.result.title })).toBeVisible()
  await expect(page.locator('p[tabindex="-1"]').filter({ hasText: first })).toBeVisible()
  await page.getByRole("button", { name: copy.form.back, exact: true }).click()
  await expect(page.getByRole("textbox", { name: copy.form.titleField, exact: true })).toHaveValue(
    second,
  )
})

test("resume an interrupted request only after an explicit action", async ({ page, request }) => {
  const card = await example(request)
  const title = `${card.title} resume ${Date.now()}`
  await fillCard(page, title, card.description)
  await page.route("**/api/v1/extract", (route) => route.abort("connectionreset"))
  const failed = page.waitForEvent("requestfailed", {
    predicate: (request) => request.url().endsWith("/api/v1/extract"),
  })
  await page.getByRole("button", { name: copy.form.submit, exact: true }).click()
  await failed
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  await page.reload()
  await expect(page.getByRole("heading", { name: copy.workspace.interrupted })).toBeVisible()
  expect(extractions).toBe(0)
  await page.unroute("**/api/v1/extract")
  const repeated = page.waitForResponse((response) => response.url().endsWith("/api/v1/extract"))
  await page.getByRole("button", { name: copy.workspace.resume, exact: true }).click()
  const response = await repeated
  expect(response.ok()).toBe(true)
  expect(response.request().postDataJSON()).toMatchObject({ title, description: card.description })
  await expect(page.getByRole("heading", { name: copy.result.title })).toBeVisible()
  expect(extractions).toBe(1)
})
test("page through saved requests on the start screen", async ({ page, request }) => {
  const card = await example(request)
  for (let index = 0; index < 21; index += 1) {
    const response = await request.post("/api/v1/extract", {
      data: {
        engine: "rules",
        category_id: card.category_id,
        title: `${card.title} history ${Date.now()} ${index}`,
        description: card.description,
      },
    })
    expect(response.ok()).toBe(true)
  }
  await page.goto("/")
  await expect(page.getByRole("heading", { name: copy.history.title })).toBeVisible()
  await expect(page.getByRole("heading", { name: copy.review.title })).toHaveCount(0)
  const first = page.locator('li[id^="run-"]').first()
  await expect(first).toBeVisible()
  const id = await first.getAttribute("id")
  await page.getByRole("button", { name: copy.review.next, exact: true }).click()
  await expect(page.locator(`#${id}`)).toHaveCount(0)
  await page.getByRole("button", { name: copy.review.previous, exact: true }).click()
  await expect(page.locator(`#${id}`)).toBeVisible()
})
