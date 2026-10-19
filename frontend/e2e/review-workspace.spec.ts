import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"
import fixture from "./fixtures/jury-route.json" with { type: "json" }

test.beforeEach(prepareStand)

test("keep an unfinished draft across reload", async ({ page }) => {
  const title = "Unfinished card"
  const description = "First line\nSecond line"
  const seller = "Unfinished line\nColor: blue"
  await fillCard(page, title, description)
  await page.getByRole("button", { name: new RegExp(`^${copy.form.details}`) }).click()
  await page.getByRole("radio", { name: copy.form.rules, exact: true }).check()
  await page.getByRole("textbox", { name: copy.form.seller, exact: true }).fill(seller)
  await page.reload()
  await expect(page.getByRole("textbox", { name: copy.form.titleField, exact: true })).toHaveValue(
    title,
  )
  await expect(
    page.getByRole("textbox", { name: copy.form.descriptionField, exact: true }),
  ).toHaveValue(description)
  await page.getByRole("button", { name: new RegExp(`^${copy.form.details}`) }).click()
  await expect(page.getByRole("radio", { name: copy.form.rules, exact: true })).toBeChecked()
  await expect(page.getByRole("textbox", { name: copy.form.seller, exact: true })).toHaveValue(
    seller,
  )
})

test("open a saved card from history and correct only its context", async ({ page, request }) => {
  const card = await example(request)
  const title = `${card.title} scoped ${Date.now()}`
  const color = card.description.split("\n").at(-1) ?? ""
  const attribute = color.slice(0, color.indexOf(":"))
  const correctedValue = color.slice(color.indexOf(":") + 1).trim()
  const description = card.description.replace(color, `${attribute}: ${fixture.unknownColor}`)
  await fillCard(page, title, description)
  const first = await submitCard(page)
  const firstId = first.values.find((value) => value.attribute === attribute)?.review_id
  expect(firstId).toBeTruthy()
  await fillCard(page, title, `${description}\nSecond seller context`)
  const second = await submitCard(page)
  const secondValue = second.values.find((value) => value.attribute === attribute)
  const secondId = secondValue?.review_id
  expect(secondId).toBeTruthy()
  expect(secondId).not.toBe(firstId)
  const current = page.locator(`[data-review-id="${secondId}"]`)
  const other = page.locator(`[data-review-id="${firstId}"]`)
  await expect(current).toBeVisible()
  await expect(other).toHaveCount(0)
  await page.getByRole("button", { name: copy.form.back, exact: true }).click()
  await expect(page.getByRole("heading", { name: copy.review.title })).toHaveCount(0)
  const runs = await (await request.get("/api/v1/runs")).json()
  const saved = runs.items.filter((item: { title: string }) => item.title === title).at(-1)
  expect(saved).toBeTruthy()
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  await page.locator(`#run-${saved.id}`).getByRole("button", { name: copy.history.open }).click()
  await expect(other).toBeVisible()
  await expect(current).toHaveCount(0)
  expect(extractions).toBe(0)
  await other
    .getByRole("textbox", {
      name: copy.review.editInline.replace("{{attribute}}", attribute),
      exact: true,
    })
    .click()
  await other.getByRole("textbox").fill(correctedValue)
  const replay = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${firstId}`) &&
      response.request().method() === "POST",
  )
  await other.getByRole("textbox").press("Enter")
  const response = await replay
  expect(response.ok()).toBe(true)
  await expect(attributeRow(page, attribute).getByRole("textbox")).toHaveValue(correctedValue)
  expect(extractions).toBe(0)
  const pending = await (
    await request.post("/api/v1/review/card", {
      data: {
        engine: "hybrid",
        category_id: second.category?.category_id,
        title,
        description: `${description}\nSecond seller context`,
      },
    })
  ).json()
  expect(
    pending.items.some(
      (item: { id: string; status: string; resolved_value: string | null }) =>
        item.id === secondId &&
        item.status === (secondValue?.acceptance === "automatic" ? "auto_accepted" : "pending") &&
        item.resolved_value === null,
    ),
  ).toBe(true)
  await page.waitForFunction(() =>
    document.getAnimations().every((animation) => animation.playState !== "running"),
  )
  const audit = await new AxeBuilder({ page }).include("#main").analyze()
  expect(
    audit.violations.map(({ id, nodes }) => ({ id, targets: nodes.map((node) => node.target) })),
  ).toEqual([])
})
