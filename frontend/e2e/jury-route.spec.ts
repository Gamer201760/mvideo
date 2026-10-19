import { execFileSync } from "node:child_process"
import { expect, test } from "@playwright/test"
import type { components } from "../src/shared/api/schema.gen"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { attributeRow, example, fillCard, prepareStand, submitCard } from "./card-scenario"
import fixture from "./fixtures/jury-route.json" with { type: "json" }

type Schemas = components["schemas"]
type ExtractResult = Schemas["ExtractResponse"]

function verifyQuotes(result: ExtractResult): void {
  expect(result.values.length).toBeGreaterThan(0)
  for (const value of [...result.values, ...(result.extra_values ?? [])]) {
    expect(value.start).toBeGreaterThanOrEqual(0)
    expect(value.end).toBeGreaterThan(value.start)
    expect(result.text.slice(value.start, value.end)).toBe(value.evidence)
    expect(value.evidence.trim().length).toBeGreaterThan(0)
  }
}

test.beforeEach(prepareStand)

test("extract a card through retrieval and show grounded attributes", async ({ page, request }) => {
  const card = await example(request)
  await fillCard(page, card.title, card.description)
  const result = await submitCard(page)
  expect(result.engine).toBe("hybrid")
  expect(result.category?.category_id).toBe(fixture.categoryId)
  expect(result.values.some((value) => value.value.includes(fixture.memory))).toBe(true)
  verifyQuotes(result)
  const categoryName = result.category?.path.split("/").at(-1)?.trim() ?? ""
  await expect(
    page
      .getByRole("region", { name: copy.result.title, exact: true })
      .getByText(categoryName, { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole("columnheader", { name: copy.risk.title })).toBeVisible()
  await expect(page.getByRole("cell", { name: /\d+\s*\/\s*100/ }).first()).toBeVisible()
  await expect(page.getByRole("dialog", { name: copy.result.textTitle })).toBeHidden()
  await expect(page.getByRole("textbox", { name: copy.form.titleField, exact: true })).toBeHidden()
  await expect(page.getByRole("list", { name: copy.progress.candidates, exact: true })).toHaveCount(
    0,
  )
  const attribute = await page
    .locator("[data-thread-source]")
    .first()
    .getAttribute("data-thread-source")
  const quoteButton = page.getByRole("button", {
    name: copy.evidence.openAttribute.replace("{{attribute}}", attribute ?? ""),
    exact: true,
  })
  await quoteButton.click()
  await expect(page.getByRole("dialog", { name: copy.result.textTitle })).toBeVisible()
  await expect(page.locator('[data-thread-target][data-active="true"]')).toBeVisible()
  await expect(page.locator("svg:visible path[pathLength]")).toHaveCount(1)
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog", { name: copy.result.textTitle })).toBeHidden()
  await expect(quoteButton).toBeFocused()
})

test("leave an absent required field empty", async ({ page, request }) => {
  const card = await example(request)
  const lines = card.description.split("\n")
  const omitted = lines.find((line) => line.includes(fixture.omittedValue))
  if (omitted === undefined) throw new Error("Synthetic battery specification is missing")
  const attribute = omitted.slice(0, omitted.indexOf(":"))
  await fillCard(page, card.title, lines.filter((line) => line !== omitted).join("\n"))
  const result = await submitCard(page)
  verifyQuotes(result)
  expect(result.missing).toContain(attribute)
  expect(result.values.some((value) => value.attribute === attribute)).toBe(false)
  await expect(page.getByText(copy.result.missingTitle, { exact: true })).toBeVisible()
  await expect(
    page.getByRole("region", { name: copy.result.title, exact: true }).getByText(attribute, {
      exact: true,
    }),
  ).toBeVisible()
})

test("correct a queued value in the main mode and reuse it after reload", async ({
  page,
  request,
}) => {
  const card = await example(request)
  const color = card.description.split("\n").at(-1) ?? ""
  const separator = color.indexOf(":")
  expect(separator).toBeGreaterThan(0)
  const attribute = color.slice(0, separator).trim()
  const correctedValue = color.slice(separator + 1).trim()
  const title = `${card.title} review ${Date.now()}`
  const description = card.description.replace(color, `${attribute}: ${fixture.unknownColor}`)
  await fillCard(page, title, description)
  const initial = await submitCard(page)
  expect(initial.engine).toBe("hybrid")
  const pending = initial.values.find((value) => value.attribute === attribute)
  expect(pending?.acceptance).toBe("automatic")
  expect(pending?.status).toBe("accepted")
  expect(pending?.review_id).toBeTruthy()
  verifyQuotes(initial)
  await expect(page.getByRole("heading", { name: copy.review.title })).toHaveCount(1)
  await page.reload()
  await expect(attributeRow(page, attribute)).toBeVisible()
  await fillCard(page, title, description)
  const repeated = await submitCard(page)
  expect(repeated.values.find((value) => value.attribute === attribute)?.review_id).toBe(
    pending?.review_id,
  )
  const row = attributeRow(page, attribute)
  await expect(row).toHaveCount(1)
  await page
    .getByRole("textbox", {
      name: copy.review.editInline.replace("{{attribute}}", attribute),
      exact: true,
    })
    .click()
  await row
    .getByRole("textbox", { name: copy.review.editInline.replace("{{attribute}}", attribute) })
    .fill(correctedValue)
  const resolved = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/review/${pending?.review_id}`),
  )
  await row.getByRole("textbox").press("Enter")
  expect((await resolved).ok()).toBe(true)
  await expect(row.getByRole("textbox")).toHaveValue(correctedValue)
  await expect(row.getByRole("textbox")).toHaveCount(1)
  const project = process.env.E2E_COMPOSE_PROJECT
  if (project !== undefined) {
    execFileSync("docker", ["compose", "-p", project, "restart", "backend"], {
      cwd: new URL("../..", import.meta.url),
      stdio: "pipe",
    })
    await expect
      .poll(async () => {
        try {
          return (await request.get("/api/v1/ready")).ok()
        } catch {
          return false
        }
      })
      .toBe(true)
  }
  let requestsAfterReload = 0
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/extract")) requestsAfterReload += 1
  })
  await page.reload()
  await expect(attributeRow(page, attribute).getByRole("textbox")).toHaveValue(correctedValue)
  expect(requestsAfterReload).toBe(0)
  await fillCard(page, title, description)
  const rerun = await submitCard(page)
  const corrected = rerun.values.find((value) => value.attribute === attribute)
  expect(corrected).toMatchObject({ value: correctedValue, source: "review", status: "accepted" })
  verifyQuotes(rerun)
  const list = await request.get("/api/v1/review", { params: { status: "corrected" } })
  expect(list.ok()).toBe(true)
  const history: Schemas["ReviewListResponse"] = await list.json()
  expect(history.items.find((item) => item.id === pending?.review_id)).toMatchObject({
    status: "corrected",
    resolved_value: correctedValue,
  })
})
