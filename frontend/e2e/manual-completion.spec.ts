import { readFile } from "node:fs/promises"
import { expect, test } from "@playwright/test"
import type { CardExport } from "../src/entities/stand/export.queries"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"
import fixture from "./fixtures/manual-completion.json" with { type: "json" }

test.beforeEach(prepareStand)

test("add a missing field, reject it, reopen history and restore the manual value", async ({
  page,
  request,
}) => {
  const card = await example(request)
  const title = `${card.title} completion ${Date.now()}`
  const color = card.description.split("\n").at(-1) ?? ""
  const attribute = color.slice(0, color.indexOf(":"))
  const evidence = fixture.evidence
  await fillCard(page, title, evidence)
  const initial = await submitCard(page)
  expect(initial.category?.category_id).toBe(card.category_id)
  expect(initial.missing).toContain(attribute)
  let extractions = 0
  let additions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
    if (request.url().endsWith("/api/v1/review/add")) additions += 1
  })
  await page
    .getByRole("button", {
      name: copy.review.addInline.replace("{{attribute}}", attribute),
      exact: true,
    })
    .click()
  const valueControl = page.getByRole("textbox", {
    name: copy.review.valueLabel.replace("{{attribute}}", attribute),
    exact: true,
  })
  await expect(valueControl).toBeFocused()
  await valueControl.fill(fixture.value)
  const quote = page.getByRole("textbox", { name: copy.review.quoteLabel, exact: true })
  await quote.fill(fixture.invalidEvidence)
  await page.getByRole("button", { name: copy.review.save, exact: true }).click()
  await expect(page.getByRole("alert")).toContainText(copy.review.quoteInvalid)
  expect(additions).toBe(0)
  await quote.fill(evidence)
  await page.getByRole("button", { name: copy.review.save, exact: true }).click()
  const row = attributeRow(page, attribute)
  await expect(row.getByRole("textbox")).toHaveValue(fixture.value)
  await expect(row).toContainText(copy.result.status.accepted)
  await expect(row).toContainText(evidence)
  await expect(page.locator("[data-review-summary]")).toBeFocused()
  await page.reload()
  await expect(row.getByRole("textbox")).toHaveValue(fixture.value)
  await expect(row.getByRole("cell").first().getByRole("button")).toHaveCount(0)
  const review = await (
    await request.post("/api/v1/review/card", {
      data: {
        engine: "hybrid",
        title,
        description: evidence,
        category_id: initial.category?.category_id,
      },
    })
  ).json()
  const item = review.items.find((item: { attribute: string }) => item.attribute === attribute)
  const rejected = await request.post(`/api/v1/review/${item.id}`, {
    data: { action: "reject", override: true, expected_value: fixture.value },
  })
  expect(rejected.ok()).toBe(true)
  await page.reload()
  await expect(row).toHaveCount(0)
  await expect(page.getByRole("region", { name: copy.review.rejectedTitle })).toContainText(
    fixture.value,
  )
  await page.reload()
  await expect(row).toHaveCount(0)
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: copy.export.download, exact: true }).click()
  const file = await download
  const path = await file.path()
  if (path === null) throw new Error("Missing downloaded card")
  const exported: CardExport = JSON.parse(await readFile(path, "utf8"))
  expect(exported.result.values.some((value) => value.attribute === attribute)).toBe(false)
  expect(exported.result.missing).toContain(attribute)
  expect(exported.decisions).toContainEqual(
    expect.objectContaining({
      attribute: attribute,
      status: "rejected",
      resolved_value: null,
    }),
  )
  await page.getByRole("button", { name: copy.form.back, exact: true }).click()
  const run = page.getByRole("listitem").filter({ has: page.getByText(title, { exact: true }) })
  await run.getByRole("button", { name: copy.history.open, exact: true }).click()
  await expect(page.getByRole("region", { name: copy.review.rejectedTitle })).toBeVisible()
  await expect(row).toHaveCount(0)
  await page
    .getByRole("button", {
      name: copy.review.restoreInline.replace("{{attribute}}", attribute),
      exact: true,
    })
    .click()
  await expect(row.getByRole("textbox")).toHaveValue(fixture.value)
  await expect(row).toContainText(copy.result.status.accepted)
  expect(extractions).toBe(0)
  expect(additions).toBe(1)
  await expect(page.locator("[data-review-summary]")).toBeFocused()
})

test("reject an automatic decision without a prior manual acceptance", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} reject automatic ${Date.now()}`, card.description)
  const result = await submitCard(page)
  const value = result.values.find((value) => value.acceptance === "automatic")
  if (value === undefined) throw new Error("Missing automatic value")
  const row = attributeRow(page, value.attribute)
  await expect(row.getByRole("cell").first().getByRole("button")).toHaveCount(0)
  const rejected = await request.post(`/api/v1/review/${value.review_id}`, {
    data: { action: "reject", override: false },
  })
  expect(rejected.ok()).toBe(true)
  await page.reload()
  await expect(row).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole("region", { name: copy.review.rejectedTitle })).toContainText(
    value.attribute,
  )
  await expect(row).toHaveCount(0)
})
