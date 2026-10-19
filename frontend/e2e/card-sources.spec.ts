import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { example, prepareStand } from "./card-scenario"

test.beforeEach(prepareStand)

test("fill an example inline and keep manual edits after reload", async ({ page, request }) => {
  const card = await example(request)
  await page.goto("/")
  const button = page.getByRole("button", {
    name: copy.form.useExample.replace("{{title}}", card.title),
    exact: true,
  })
  await button.click()
  const title = page.getByRole("textbox", { name: copy.form.titleField, exact: true })
  const description = page.getByRole("textbox", { name: copy.form.descriptionField, exact: true })
  await expect(title).toHaveValue(card.title)
  await expect(description).toHaveValue(card.description)
  await expect(button).toHaveAttribute("aria-pressed", "true")
  const edited = `${card.title} edited`
  await title.fill(edited)
  await expect(button).toHaveAttribute("aria-pressed", "false")
  await page.reload()
  await expect(title).toHaveValue(edited)
  await expect(description).toHaveValue(card.description)
})

test("pause the illustration while typing and respect reduced motion", async ({ page }) => {
  await page.goto("/")
  const art = page.locator("[data-card-flow]")
  const thread = art.locator("[pathLength]").first()
  await expect(art).toBeVisible()
  await expect(thread).toHaveCSS("animation-play-state", "running")
  await page.getByRole("textbox", { name: copy.form.titleField, exact: true }).focus()
  await expect(thread).toHaveCSS("animation-play-state", "paused")
  await page.getByRole("button", { name: copy.landing.pause, exact: true }).click()
  await expect(thread).toHaveCSS("animation-play-state", "paused")
  await page.getByRole("button", { name: copy.landing.resume, exact: true }).click()
  await expect(thread).toHaveCSS("animation-play-state", "running")
  await page.emulateMedia({ reducedMotion: "reduce" })
  await expect(page.getByRole("button", { name: copy.landing.pause, exact: true })).toBeHidden()
  await expect
    .poll(() => art.evaluate((element) => element.getAnimations({ subtree: true }).length))
    .toBe(0)
})
