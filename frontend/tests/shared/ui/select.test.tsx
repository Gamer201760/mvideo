import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { Select } from "@/shared/ui"

type Choice = "a" | "b" | "c"

function Probe() {
  const [value, setValue] = useState<Choice | null>(null)
  return (
    <Select
      label="L1"
      placeholder="P1"
      value={value}
      onChange={setValue}
      options={[
        { value: "a", label: "A1" },
        { value: "b", label: "B1", hint: "H2" },
        { value: "c", label: "C1" },
      ]}
    />
  )
}

describe("Select", () => {
  it("opens a listbox on click and picks an option", async () => {
    render(<Probe />)
    const trigger = screen.getByRole("button", { name: /L1/ })
    expect(trigger.textContent).toContain("P1")
    await userEvent.click(trigger)
    await userEvent.click(screen.getByRole("option", { name: /B1/ }))
    expect(trigger.textContent).toContain("B1")
    expect(trigger.getAttribute("aria-expanded")).toBe("false")
  })

  it("works from the keyboard and returns focus on Escape", async () => {
    render(<Probe />)
    const trigger = screen.getByRole("button", { name: /L1/ })
    trigger.focus()
    await userEvent.keyboard("{ArrowDown}")
    const list = screen.getByRole("listbox")
    expect(document.activeElement).toBe(list)
    await userEvent.keyboard("{End}{Enter}")
    expect(trigger.textContent).toContain("C1")
    expect(document.activeElement).toBe(trigger)
    await userEvent.keyboard("{ArrowDown}{Home}{Escape}")
    expect(trigger.textContent).toContain("C1")
    expect(document.activeElement).toBe(trigger)
  })
})
