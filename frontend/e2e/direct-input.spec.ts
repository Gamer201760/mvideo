import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"

test.beforeEach(prepareStand)

test("edit the existing input, save on Enter and keep the value after reload", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} direct input ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((item) => item.review_id != null)
  if (value === undefined) throw new Error("An editable value is required")
  const row = attributeRow(page, value.attribute)
  const input = row.getByRole("textbox", {
    name: copy.review.editInline.replace("{{attribute}}", value.attribute),
    exact: true,
  })
  await expect(input).toHaveValue(value.value)
  await expect(row.getByRole("cell").first().getByRole("button")).toHaveCount(0)
  const height = (await row.boundingBox())?.height ?? 0
  expect(height).toBeGreaterThan(0)
  let writes = 0
  page.on("request", (request) => {
    if (request.url().endsWith(`/api/v1/review/${value.review_id}`) && request.method() === "POST")
      writes += 1
  })
  await input.focus()
  await input.press("Enter")
  await input.press("Tab")
  expect(writes).toBe(0)
  const changed = `${value.value} edited`
  await input.fill(changed)
  expect((await row.boundingBox())?.height).toBeCloseTo(height, 1)
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${value.review_id}`) &&
      response.request().method() === "POST",
  )
  await input.press("Enter")
  await input.press("Tab")
  expect((await saved).ok()).toBe(true)
  await expect(row).toContainText(copy.result.status.accepted)
  expect(writes).toBe(1)
  await page.reload()
  await expect(input).toHaveValue(changed)
})

test("save on blur without moving focus and cancel a draft with Escape", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 375, height: 900 })
  const card = await example(request)
  await fillCard(page, `${card.title} blur input ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const values = result.values.filter((value) => value.review_id != null)
  const first = values[0]
  const second = values[1]
  if (first === undefined || second === undefined)
    throw new Error("Two editable values are required")
  const input = attributeRow(page, first.attribute).getByRole("textbox")
  const next = attributeRow(page, second.attribute).getByRole("textbox")
  await input.fill(`${first.value} cancelled`)
  await input.press("Escape")
  await expect(input).toHaveValue(first.value)
  await input.fill("")
  await next.focus()
  await expect(input).toHaveValue(first.value)
  const changed = `${first.value} saved on blur`
  await input.fill(changed)
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${first.review_id}`) &&
      response.request().method() === "POST",
  )
  await next.focus()
  expect((await saved).ok()).toBe(true)
  await expect(next).toBeFocused()
  await expect(input).not.toHaveAttribute("readonly")
  await page.reload()
  await expect(input).toHaveValue(changed)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test("keep a failed draft visible and retry saving it", async ({ page, request }) => {
  const card = await example(request)
  await fillCard(page, `${card.title} failed input ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((item) => item.review_id != null)
  if (value === undefined) throw new Error("An editable value is required")
  const row = attributeRow(page, value.attribute)
  const input = row.getByRole("textbox")
  const changed = `${value.value} retry`
  await page.route(`**/api/v1/review/${value.review_id}`, (route) => route.abort("connectionreset"))
  await input.fill(changed)
  await input.press("Enter")
  await expect(input).toHaveAttribute("aria-invalid", "true")
  await expect(input).toHaveValue(changed)
  await expect(input).not.toHaveAttribute("readonly")
  await page.unroute(`**/api/v1/review/${value.review_id}`)
  await input.press("Enter")
  await expect(input).not.toHaveAttribute("aria-invalid", "true")
  await expect(row).toContainText(copy.result.status.accepted)
  await page.reload()
  await expect(input).toHaveValue(changed)
})
