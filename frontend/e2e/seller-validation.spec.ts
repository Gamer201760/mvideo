import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { example, prepareStand } from "./card-scenario"

test.beforeEach(prepareStand)

test("keep invalid seller lines through reload and block requests until corrected", async ({
  page,
  request,
}) => {
  const card = await example(request)
  const extractionRequests: string[] = []
  page.on("request", (sent) => {
    if (sent.method() === "POST" && sent.url().includes("/api/v1/extract"))
      extractionRequests.push(sent.url())
  })
  await page.goto("/")
  await page.getByRole("textbox", { name: copy.form.titleField, exact: true }).fill(card.title)
  await page
    .getByRole("textbox", { name: copy.form.descriptionField, exact: true })
    .fill(card.description)
  const details = page.getByRole("button", { name: new RegExp(copy.form.details) })
  await details.click()
  const seller = page.getByRole("textbox", { name: copy.form.seller, exact: true })
  const raw = "Color: black\n\nBroken line\n: value\nWidth:"
  await seller.fill(raw)
  await seller.press("Tab")
  for (const [line, reason] of [
    [3, copy.form.sellerErrors.missingSeparator],
    [4, copy.form.sellerErrors.missingName],
    [5, copy.form.sellerErrors.missingValue],
  ] as const) {
    const message = copy.form.sellerErrors.line
      .replace("{{line, number}}", String(line))
      .replace("{{reason}}", reason)
    await expect(page.getByText(message, { exact: true })).toBeVisible()
  }
  await page.reload()
  await expect(seller).toHaveValue(raw)
  await expect(seller).toHaveAttribute("aria-invalid", "true")
  await details.focus()
  await page.keyboard.press("Enter")
  await expect(details).toHaveAttribute("aria-expanded", "false")
  await page.getByRole("button", { name: copy.form.submit, exact: true }).click()
  await expect(details).toHaveAttribute("aria-expanded", "true")
  await expect(seller).toBeFocused()
  await expect(seller).toHaveValue(raw)
  expect(extractionRequests).toEqual([])
  await seller.press("Control+Enter")
  await expect(seller).toBeFocused()
  expect(extractionRequests).toEqual([])
  await seller.fill("Color: black\nWidth: 90 mm\nURL: https://example.com")
  await expect(page.getByRole("alert")).toHaveCount(0)
  const received = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/extract") && response.request().method() === "POST",
  )
  await page.getByRole("button", { name: copy.form.submit, exact: true }).click()
  const response = await received
  expect(response.ok(), await response.text()).toBe(true)
  expect(response.request().postDataJSON().seller_params).toEqual([
    { name: "Color", value: "black", unit: null },
    { name: "Width", value: "90 mm", unit: null },
    { name: "URL", value: "https://example.com", unit: null },
  ])
})
