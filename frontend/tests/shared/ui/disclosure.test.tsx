import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { Disclosure } from "@/shared/ui"

describe("Disclosure", () => {
  it("toggles its panel and keeps aria-expanded in sync", async () => {
    const user = userEvent.setup()
    render(
      <Disclosure label="More" hint="Optional">
        <p>Body</p>
      </Disclosure>,
    )
    const trigger = screen.getByRole("button", { name: /More/ })
    expect(trigger.getAttribute("aria-expanded")).toBe("false")
    expect(screen.queryByText("Body")).toBeNull()
    await user.click(trigger)
    expect(trigger.getAttribute("aria-expanded")).toBe("true")
    expect(screen.getByText("Body")).toBeTruthy()
    expect(trigger.getAttribute("aria-controls")).toBe(screen.getByText("Body").parentElement?.id)
  })

  it("closes at once when toggled from the keyboard", async () => {
    const user = userEvent.setup()
    render(
      <Disclosure label="More" defaultOpen>
        <p>Body</p>
      </Disclosure>,
    )
    screen.getByRole("button", { name: /More/ }).focus()
    await user.keyboard("{Enter}")
    expect(screen.queryByText("Body")).toBeNull()
  })
})
