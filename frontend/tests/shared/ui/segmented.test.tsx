import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { Segmented, type SegmentedDisplay } from "@/shared/ui"

type Choice = "a" | "b"

function Probe({ display }: { readonly display: SegmentedDisplay }) {
  const [value, setValue] = useState<Choice>("a")
  return (
    <Segmented
      label="G1"
      display={display}
      value={value}
      onChange={setValue}
      options={[
        { value: "a", label: "A1", short: "S1", icon: "theme-light" },
        { value: "b", label: "B1", short: "S2", icon: "theme-dark" },
      ]}
    />
  )
}

describe("Segmented", () => {
  it("is a named radio group that moves the selection on click", async () => {
    render(<Probe display="label" />)
    expect(screen.getByRole("group", { name: "G1" })).toBeTruthy()
    const second = screen.getByRole("radio", { name: "B1" }) as HTMLInputElement
    await userEvent.click(second)
    expect(second.checked).toBe(true)
    expect(second.closest("label")?.dataset.checked).toBe("true")
  })

  it("keeps the full name accessible when only icons or short codes are shown", () => {
    const { unmount } = render(<Probe display="icon" />)
    expect(screen.getByRole("radio", { name: "A1" })).toBeTruthy()
    expect(screen.getByText("A1").className).toBe("visually-hidden")
    unmount()
    render(<Probe display="short" />)
    expect(screen.getByRole("radio", { name: "B1" })).toBeTruthy()
    expect(screen.getByText("S2").getAttribute("aria-hidden")).toBe("true")
  })
})
