import { readFile } from "node:fs/promises"
import { type Download, expect, test } from "@playwright/test"
import type { CardExport } from "../src/entities/stand/export.queries"
import common from "../src/shared/i18n/locales/ru/common.json" with { type: "json" }
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"
import fixture from "./fixtures/jury-route.json" with { type: "json" }

async function readExport(download: Download): Promise<CardExport> {
  expect(await download.failure()).toBeNull()
  expect(download.suggestedFilename()).toMatch(/^card-[\p{L}\p{N}_-]+\.json$/u)
  const path = await download.path()
  if (path === null) throw new Error("Downloaded file is missing")
  return JSON.parse(await readFile(path, "utf8"))
}

test.beforeEach(prepareStand)

test("download the corrected open result without extracting again", async ({ page, request }) => {
  const card = await example(request)
  const title = `${card.title} export / <test> ${Date.now()}`
  await fillCard(page, title, card.description)
  const initial = await submitCard(page)
  const value = initial.values.find((item) => item.review_id != null)
  if (value?.review_id == null) throw new Error("A pending value is required")
  const row = attributeRow(page, value.attribute)
  const corrected = `${value.value} checked`
  await row
    .getByRole("textbox", {
      name: copy.review.editInline.replace("{{attribute}}", value.attribute),
      exact: true,
    })
    .click()
  await row.getByRole("textbox").fill(corrected)
  const persisted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/review/${value.review_id}`) &&
      response.request().method() === "POST",
  )
  await row.getByRole("textbox").press("Enter")
  const decision = await persisted
  expect(decision.ok()).toBe(true)
  expect(await decision.json()).toMatchObject({ resolved_value: corrected, status: "corrected" })
  await expect(row.getByRole("textbox")).toHaveValue(corrected)
  await page.reload()
  await expect(page.getByRole("heading", { name: copy.result.title })).toBeVisible()
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: copy.export.download, exact: true }).click()
  const saved = await readExport(await download)
  expect(saved.schema_version).toBe(1)
  expect(saved.input).toMatchObject({ title, description: card.description, engine: "hybrid" })
  expect(saved.result.category?.category_id).toBe(initial.category?.category_id)
  expect(saved.result.values.find((item) => item.attribute === value.attribute)).toMatchObject({
    value: corrected,
    source: "review",
    status: "accepted",
  })
  expect(saved.decisions).toContainEqual(
    expect.objectContaining({
      id: value.review_id,
      resolved_value: corrected,
      status: "corrected",
    }),
  )
  for (const item of [...saved.result.values, ...(saved.result.extra_values ?? [])]) {
    expect(saved.result.text.slice(item.start, item.end)).toBe(item.evidence)
  }
  expect(extractions).toBe(0)
})

test("download history with the latest decisions for its exact card", async ({ page, request }) => {
  const card = await example(request)
  const title = `${card.title} history export ${Date.now()}`
  const color = card.description.split("\n").at(-1) ?? ""
  const attribute = color.slice(0, color.indexOf(":"))
  const corrected = color.slice(color.indexOf(":") + 1).trim()
  const input = {
    engine: "hybrid",
    title,
    category_id: card.category_id,
    description: card.description.replace(color, `${attribute}: ${fixture.unknownColor}`),
  }
  const initial = await (await request.post("/api/v1/extract", { data: input })).json()
  const value = initial.values.find((item: { attribute: string }) => item.attribute === attribute)
  expect(value.review_id).toBeTruthy()
  const runs = await (await request.get("/api/v1/runs")).json()
  const run = runs.items.find((item: { title: string }) => item.title === title)
  expect(run).toBeTruthy()
  const other = await request.post("/api/v1/extract", {
    data: { ...input, description: `${input.description}\nAnother seller context` },
  })
  expect(other.ok()).toBe(true)
  const decision = await request.post(`/api/v1/review/${value.review_id}`, {
    data: { action: "correct", value: corrected },
  })
  expect(decision.ok()).toBe(true)
  await page.goto("/")
  let extractions = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) extractions += 1
  })
  const download = page.waitForEvent("download")
  await page.locator(`#run-${run.id}`).getByRole("button", { name: copy.export.download }).click()
  const saved = await readExport(await download)
  expect(saved.input).toMatchObject(input)
  expect(saved.result.values.find((item) => item.attribute === attribute)).toMatchObject({
    value: corrected,
    source: "review",
    status: "accepted",
  })
  expect(saved.decisions.map((item) => item.id)).toEqual([value.review_id])
  expect(saved.result.values.some((item) => item.status === "review")).toBe(true)
  expect(extractions).toBe(0)
  await expect(page.getByRole("heading", { name: copy.history.title })).toBeVisible()
})

test("offer retry without downloading when decisions cannot be checked", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, `${card.title} export failure ${Date.now()}`, card.description)
  await submitCard(page)
  await expect(page.getByRole("table").first()).toBeVisible()
  await page.route("**/api/v1/review/card", (route) => route.abort("connectionreset"))
  let downloads = 0
  page.on("download", () => {
    downloads += 1
  })
  await page.getByRole("button", { name: copy.export.download, exact: true }).click()
  const error = page.getByRole("alert").filter({ hasText: copy.export.failed })
  await expect(error).toBeVisible()
  expect(downloads).toBe(0)
  await page.unroute("**/api/v1/review/card")
  const download = page.waitForEvent("download")
  await error.getByRole("button", { name: common.action.retry, exact: true }).click()
  expect((await readExport(await download)).input.title).toContain("export failure")
  await expect(error).toHaveCount(0)
})
