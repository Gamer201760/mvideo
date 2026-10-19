import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"

test.beforeEach(prepareStand)

test("accept by threshold and edit without creating a prior human decision", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} automatic ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((item) => item.acceptance === "automatic")
  if (value === undefined) throw new Error("An automatically accepted value is required")
  expect(result.threshold).toBe(0.95)
  expect(value.source).not.toBe("review")
  const row = attributeRow(page, value.attribute)
  await expect(row).toContainText(copy.result.status.automatic)
  await row
    .getByRole("textbox", {
      name: copy.review.editInline.replace("{{attribute}}", value.attribute),
      exact: true,
    })
    .click()
  const changed = `${value.value} adjusted`
  await row.getByRole("textbox").fill(changed)
  const saved = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/review/${value.review_id}`),
  )
  await row.getByRole("textbox").press("Enter")
  const response = await saved
  expect(response.ok()).toBe(true)
  expect(response.request().postDataJSON()).toMatchObject({ action: "correct", override: false })
  await expect(row).toContainText(copy.result.status.accepted)
  await page.reload()
  await expect(row.getByRole("textbox")).toHaveValue(changed)
  await expect(row).toContainText(copy.result.status.accepted)
})

test("confirm a reviewed value unchanged and edit it only through an explicit action", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} inline ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find(
    (value) => value.acceptance === "review" && value.review_id !== null,
  )
  if (value === undefined) throw new Error("A reviewed field is required")
  const score = `${Math.round((value.risk?.score ?? 0) * 100)} / 100`
  const row = attributeRow(page, value.attribute)
  const edit = row.getByRole("textbox", {
    name: copy.review.editInline.replace("{{attribute}}", value.attribute),
    exact: true,
  })
  await expect(row.getByRole("textbox")).toHaveCount(1)
  await expect(row.getByRole("cell").filter({ hasText: score })).toBeVisible()
  await expect(page.getByText(copy.source.hybrid, { exact: true })).toHaveCount(0)
  const box = await row.boundingBox()
  expect(box?.height).toBeLessThanOrEqual(88)
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  const accepted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${value.review_id}`) &&
      response.request().method() === "POST",
  )
  await row
    .getByRole("button", {
      name: copy.review.acceptInline.replace("{{attribute}}", value.attribute),
      exact: true,
    })
    .click()
  expect((await accepted).ok()).toBe(true)
  await expect(row.getByRole("textbox")).toHaveValue(value.value)
  await expect(row).toContainText(copy.result.status.accepted)
  await expect(row).toContainText(score)
  await page.reload()
  await expect(row.getByRole("textbox")).toHaveValue(value.value)
  await expect(edit).toBeEnabled()
  await edit.click()
  const editor = row.getByRole("textbox")
  await expect(editor).toBeFocused()
  const changed = `${value.value} verified`
  await editor.fill(changed)
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${value.review_id}`) &&
      response.request().method() === "POST",
  )
  await row.getByRole("textbox").press("Enter")
  const response = await saved
  expect(response.ok()).toBe(true)
  expect(response.request().postDataJSON()).toMatchObject({
    action: "correct",
    value: changed,
    override: true,
    expected_value: value.value,
  })
  await expect(row.getByRole("textbox")).toHaveValue(changed)
  await expect(editor).toHaveValue(changed)
  await expect(edit).toBeFocused()
  await page.reload()
  await expect(row.getByRole("textbox")).toHaveValue(changed)
  expect(extractions).toBe(0)
})

test("cancel an inline edit on mobile without changing the original value", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 375, height: 900 })
  const card = await example(request)
  await fillCard(page, `${card.title} cancel ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((value) => value.review_id !== null)
  if (value === undefined) throw new Error("A pending field is required")
  const row = attributeRow(page, value.attribute)
  let changes = 0
  page.on("request", (request) => {
    if (/\/review\/[^/]+$/.test(request.url()) && request.method() === "POST") changes += 1
  })
  const edit = row.getByRole("textbox", {
    name: copy.review.editInline.replace("{{attribute}}", value.attribute),
    exact: true,
  })
  await edit.click()
  await row.getByRole("textbox").fill("")
  await expect(row.getByRole("textbox")).toHaveValue("")
  await row.getByRole("textbox").press("Escape")
  await expect(row.getByRole("textbox")).toHaveCount(1)
  await expect(edit).toBeFocused()
  await expect(row.getByRole("textbox")).toHaveValue(value.value)
  expect(changes).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  const explain = row.getByRole("button", {
    name: copy.risk.explain.replace("{{attribute}}", value.attribute),
    exact: true,
  })
  await expect(explain).toHaveAttribute("aria-expanded", "false")
  await explain.click()
  await expect(explain).toHaveAttribute("aria-expanded", "true")
  await explain.press("Enter")
  await expect(explain).toHaveAttribute("aria-expanded", "false")
})
