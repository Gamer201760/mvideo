import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { NAMESPACES } from "@/shared/i18n/resources"

const SOURCES = resolve(process.cwd(), "src")
const LOCALES = join(SOURCES, "shared/i18n/locales/en")
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/
const FULL_KEY = /["'`](\w+):([\w.]+)["'`]/g
const KEY_PREFIX = /`(\w+):([\w.]*)\$\{/g
const HTML_META_KEYS = new Set(["common:meta.description"])

type Tree = { readonly [key: string]: unknown }

function leafKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "object" && value !== null
      ? leafKeys(value as Tree, `${prefix}${key}.`)
      : [`${prefix}${key}`.replace(PLURAL_SUFFIX, "")],
  )
}

function sources(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.tsx?$/.test(entry) ? [readFileSync(path, "utf8")] : []
  })
}

const texts = sources(SOURCES)
const fullKeys = new Set(
  texts.flatMap((text) => [...text.matchAll(FULL_KEY)].map((match) => `${match[1]}:${match[2]}`)),
)
const prefixes = texts.flatMap((text) =>
  [...text.matchAll(KEY_PREFIX)].map((match) => `${match[1]}:${match[2]}`),
)

function isUsed(key: string): boolean {
  return (
    HTML_META_KEYS.has(key) || fullKeys.has(key) || prefixes.some((item) => key.startsWith(item))
  )
}

describe("dictionary usage", () => {
  it.each(NAMESPACES)("has no unused keys in %s", (namespace) => {
    const tree = JSON.parse(readFileSync(join(LOCALES, `${namespace}.json`), "utf8")) as Tree
    const keys = [...new Set(leafKeys(tree))].map((key) => `${namespace}:${key}`)
    expect(keys.filter((key) => !isUsed(key))).toEqual([])
  })
})
