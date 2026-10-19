export interface Thread {
  readonly key: string
  readonly path: string
  readonly knotX: number
  readonly knotY: number
  readonly arrow: string
}

export interface ThreadMetrics {
  readonly lead: number
  readonly rowAnchor: number
}

const LANE = "[data-thread-lane]"

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), Math.max(low, high))
}

function byKey(root: HTMLElement, attribute: string, key: string): HTMLElement | undefined {
  return [...root.querySelectorAll<HTMLElement>(`[${attribute}]`)].find(
    (element) => element.getAttribute(attribute) === key,
  )
}

export function measureThread(root: HTMLElement, key: string, metrics: ThreadMetrics) {
  const source = byKey(root, "data-thread-source", key)
  const target = byKey(root, "data-thread-target", key)
  const sourceLane = source?.closest(LANE)
  const targetLane = target?.closest(LANE)
  if (!source || !target || !sourceLane || !targetLane) return null
  const box = root.getBoundingClientRect()
  const line = target.getClientRects()[0] ?? target.getBoundingClientRect()
  const row = source.getBoundingClientRect()
  const lane = targetLane.getBoundingClientRect()
  const rowLane = sourceLane.getBoundingClientRect()
  const direction = lane.right <= rowLane.left ? 1 : lane.left >= rowLane.right ? -1 : 0
  if (direction === 0) return null
  const fromX = (direction === 1 ? lane.right : lane.left) - box.left
  const scroll = target.closest("[data-evidence-scroll]")?.getBoundingClientRect() ?? lane
  const fromY = clamp(
    line.top + line.height / 2 - box.top,
    scroll.top - box.top + metrics.rowAnchor,
    scroll.bottom - box.top - metrics.rowAnchor,
  )
  const toX = (direction === 1 ? rowLane.left : rowLane.right) - box.left
  const toY = row.top + Math.min(row.height / 2, metrics.rowAnchor) - box.top
  if (Math.abs(toX - fromX) < metrics.lead) return null
  const bend = (toX - fromX) / 2
  const tip = metrics.lead / 2
  const thread: Thread = {
    key,
    path: `M ${fromX - direction * metrics.lead} ${fromY} H ${fromX} C ${fromX + bend} ${fromY} ${toX - bend} ${toY} ${toX} ${toY}`,
    knotX: toX,
    knotY: toY,
    arrow: `M ${toX - direction * tip} ${toY - tip} L ${toX} ${toY} L ${toX - direction * tip} ${toY + tip}`,
  }
  return thread
}
