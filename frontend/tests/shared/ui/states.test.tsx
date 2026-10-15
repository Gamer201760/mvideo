import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import ru from "@/shared/i18n/locales/ru/common.json"
import { Button, EmptyState, ErrorState, NoValue } from "@/shared/ui"

describe("ErrorState", () => {
  it("announces the error and retries on click", async () => {
    const retry = vi.fn()
    render(<ErrorState title="E1" onRetry={retry} />)
    expect(screen.getByRole("alert").textContent).toContain("E1")
    await userEvent.click(screen.getByRole("button", { name: ru.action.retry }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it("keeps the retry button busy while pending and ignores clicks", async () => {
    const retry = vi.fn()
    render(<ErrorState title="E1" onRetry={retry} retryPending />)
    const button = screen.getByRole("button", { name: ru.action.retry })
    expect(button.getAttribute("aria-busy")).toBe("true")
    await userEvent.click(button)
    expect(retry).not.toHaveBeenCalled()
  })
})

describe("Button", () => {
  it("keeps its label in the tree while pending so the width does not jump", () => {
    render(<Button pending>L1</Button>)
    const button = screen.getByRole("button", { name: "L1" })
    expect(button.querySelector('[data-icon="loader"]')).not.toBeNull()
    expect(button.getAttribute("type")).toBe("button")
  })
})

describe("EmptyState and NoValue", () => {
  it("renders the empty state with a decorative icon", () => {
    render(<EmptyState icon="empty" title="T1" description="D1" />)
    expect(screen.getByText("T1")).toBeTruthy()
    expect(document.querySelector('[data-icon="empty"]')?.getAttribute("aria-hidden")).toBe("true")
  })

  it("shows the dictionary placeholder instead of a dash", () => {
    render(<NoValue />)
    expect(screen.getByText(ru.value.none)).toBeTruthy()
    expect(screen.getByText(ru.value.noneLabel).className).toBe("visually-hidden")
  })
})
