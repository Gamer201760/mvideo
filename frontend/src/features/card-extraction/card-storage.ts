import type { ExtractInput, ExtractResult } from "@/entities/stand"

export interface CardDraft {
  readonly engine: "hybrid" | "rules"
  readonly title: string
  readonly description: string
  readonly seller: string
  readonly category: string | null
}

export interface CardSession {
  readonly input: ExtractInput
  readonly result: ExtractResult
}

export interface CardWorkspace {
  readonly completed: CardSession | null
  readonly pending: ExtractInput | null
  readonly view: "draft" | "result"
}

const DRAFT_KEY = "card-draft-v1"
const SESSION_KEY = "card-session-v1"
const WORKSPACE_KEY = "card-workspace-v2"

function read(key: string): unknown {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null")
  } catch {
    return null
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    return
  }
}

export function readDraft(): CardDraft {
  const value = read(DRAFT_KEY) as Partial<CardDraft> | null
  return {
    engine: value?.engine === "rules" ? "rules" : "hybrid",
    title: typeof value?.title === "string" ? value.title : "",
    description: typeof value?.description === "string" ? value.description : "",
    seller: typeof value?.seller === "string" ? value.seller : "",
    category: typeof value?.category === "string" ? value.category : null,
  }
}

export function saveDraft(draft: CardDraft) {
  write(DRAFT_KEY, draft)
}

function readSession(): CardSession | null {
  const value = read(SESSION_KEY) as Partial<CardSession> | null
  if (
    typeof value?.input?.title !== "string" ||
    typeof value.result?.text !== "string" ||
    !Array.isArray(value.result.values) ||
    !Array.isArray(value.result.missing)
  )
    return null
  return value as CardSession
}

export function readWorkspace(): CardWorkspace {
  const value = read(WORKSPACE_KEY) as Partial<CardWorkspace> | null
  if (value?.view === "draft" || value?.view === "result") {
    return {
      view: value.view,
      pending: typeof value.pending?.title === "string" ? value.pending : null,
      completed: typeof value.completed?.result?.text === "string" ? value.completed : null,
    }
  }
  const completed = readSession()
  return { completed, pending: null, view: completed === null ? "draft" : "result" }
}

export function saveWorkspace(workspace: CardWorkspace) {
  write(WORKSPACE_KEY, workspace)
}
