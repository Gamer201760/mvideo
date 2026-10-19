import { afterEach, describe, expect, it } from "vitest"
import { measureThread } from "@/shared/motion/thread-layer/thread-geometry"

const METRICS = { lead: 12, rowAnchor: 22 }

function box(element: Element, left: number, top: number, width: number, height: number) {
  const rect = DOMRect.fromRect({ x: left, y: top, width, height })
  Object.assign(element, {
    getBoundingClientRect: () => rect,
    getClientRects: () => [rect],
  })
}

function board(textLeft: number, rowLeft: number) {
  document.body.innerHTML = `
    <div id="root">
      <section id="text" data-thread-lane><mark id="mark" data-thread-target="Color">black</mark></section>
      <section id="table" data-thread-lane><div id="row" data-thread-source="Color"></div></section>
    </div>`
  const at = (id: string) => document.getElementById(id) as HTMLElement
  box(at("root"), 0, 0, 1000, 800)
  box(at("text"), textLeft, 0, 400, 600)
  box(at("mark"), textLeft + 40, 100, 60, 20)
  box(at("table"), rowLeft, 0, 500, 800)
  box(at("row"), rowLeft + 20, 300, 460, 64)
  return at("root")
}

describe("measureThread", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("runs from the text lane edge at the quote line to the row lane edge", () => {
    const thread = measureThread(board(0, 448), "Color", METRICS)
    expect(thread?.path.startsWith("M 388 110 H 400 C")).toBe(true)
    expect(thread?.path.endsWith("448 322")).toBe(true)
    expect([thread?.knotX, thread?.knotY]).toEqual([448, 322])
  })

  it("draws nothing when the lanes are stacked or the key is unknown", () => {
    expect(measureThread(board(0, 0), "Color", METRICS)).toBeNull()
    expect(measureThread(board(0, 448), "Brand", METRICS)).toBeNull()
  })

  it("points from a source panel on the right back to the selected row", () => {
    const thread = measureThread(board(548, 0), "Color", METRICS)
    expect(thread?.path.startsWith("M 560 110 H 548 C")).toBe(true)
    expect(thread?.path.endsWith("500 322")).toBe(true)
    expect(thread?.arrow).toBe("M 506 316 L 500 322 L 506 328")
  })
})
