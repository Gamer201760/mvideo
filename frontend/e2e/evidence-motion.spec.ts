import { expect, test } from "@playwright/test"
import copy from "../src/shared/i18n/locales/ru/stand.json" with { type: "json" }
import { example, fillCard, prepareStand, submitCard } from "./card-scenario"

test.beforeEach(prepareStand)

test("animate both layout directions and allow reopening during a transition", async ({
  page,
  request,
}) => {
  const card = await example(request)
  await fillCard(page, card.title, card.description)
  await submitCard(page)
  const open = page.getByRole("button", { name: copy.evidence.open, exact: true })
  const panel = page.getByRole("dialog", { name: copy.result.textTitle, exact: true })
  const close = panel.getByRole("button", { name: copy.evidence.close, exact: true })
  const mode = () => page.evaluate(() => document.documentElement.dataset.viewTransition ?? "")
  await expect.poll(mode).toBe("")
  await open.click()
  await expect(panel).toBeVisible()
  await expect.poll(mode).toBe("evidence-open")
  await expect
    .poll(() =>
      page.evaluate(() =>
        document
          .getAnimations()
          .some((animation) => animation.effect?.getTiming().duration === 480),
      ),
    )
    .toBe(true)
  await expect.poll(mode).toBe("")
  await close.click()
  await expect.poll(mode).toBe("evidence-close")
  await expect
    .poll(() =>
      page.evaluate(() =>
        document
          .getAnimations()
          .some((animation) => animation.effect?.getTiming().duration === 360),
      ),
    )
    .toBe(true)
  await open.click()
  await expect(panel).toBeVisible()
  await expect.poll(mode).toBe("")
  await page.keyboard.press("Escape")
  await expect(panel).toBeHidden()
  await expect(open).toBeFocused()
  await expect.poll(mode).toBe("")
  await open.press("Enter")
  await expect(panel).toBeVisible()
  await expect.poll(mode).toBe("")
})

test("keep a usable animated fallback without View Transitions", async ({ page, request }) => {
  await page.addInitScript(() => {
    Object.defineProperty(document, "startViewTransition", { value: undefined })
  })
  const card = await example(request)
  await fillCard(page, card.title, card.description)
  await submitCard(page)
  const open = page.getByRole("button", { name: copy.evidence.open, exact: true })
  const panel = page.getByRole("dialog", { name: copy.result.textTitle, exact: true })
  await open.click()
  await expect(panel).toBeVisible()
  await expect(panel).toHaveCSS("animation-duration", "0.48s")
  await panel.getByRole("button", { name: copy.evidence.close, exact: true }).click()
  await expect(panel).toHaveCSS("animation-duration", "0.36s")
  await expect(panel).toBeHidden()
  await expect(open).toBeFocused()
  await page.emulateMedia({ reducedMotion: "reduce" })
  await open.click()
  await expect(panel).toBeVisible()
  await expect(panel).toHaveCSS("animation-duration", "0.001s")
})
