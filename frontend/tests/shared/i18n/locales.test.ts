import { readdirSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { NAMESPACES } from "@/shared/i18n/resources"

const LOCALES_DIR = resolve(process.cwd(), "src/shared/i18n/locales")
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/

type Tree = { readonly [key: string]: unknown }

function leafKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "object" && value !== null
      ? leafKeys(value as Tree, `${prefix}${key}.`)
      : [`${prefix}${key}`.replace(PLURAL_SUFFIX, "")],
  )
}

function leafValues(tree: Tree): string[] {
  return Object.values(tree).flatMap((value) =>
    typeof value === "object" && value !== null ? leafValues(value as Tree) : [String(value)],
  )
}

const read = (locale: string, file: string) =>
  JSON.parse(readFileSync(join(LOCALES_DIR, locale, file), "utf8")) as Tree
const keysOf = (locale: string, file: string) => [...new Set(leafKeys(read(locale, file)))].sort()
const filesOf = (locale: string) =>
  readdirSync(join(LOCALES_DIR, locale))
    .filter((file) => file.endsWith(".json"))
    .sort()

describe("dictionaries", () => {
  it("has the same namespace files for ru and en", () => {
    expect(readdirSync(LOCALES_DIR).sort()).toEqual(["en", "ru"])
    expect(filesOf("ru")).toEqual(filesOf("en"))
  })

  it("registers every namespace file in resources", () => {
    expect(filesOf("en")).toEqual(NAMESPACES.map((namespace) => `${namespace}.json`).sort())
  })

  it.each(filesOf("en"))("has identical keys in ru and en for %s", (file) => {
    expect(keysOf("ru", file)).toEqual(keysOf("en", file))
  })

  it.each(
    filesOf("en").flatMap((file) => [
      ["ru", file],
      ["en", file],
    ]),
  )("%s/%s has no empty values and no internal identifiers", (locale, file) => {
    const values = leafValues(read(locale, file))
    expect(values.filter((value) => value.trim() === "")).toEqual([])
    expect(values.filter((value) => /\b[a-z]+_[a-z_]+\b/.test(value))).toEqual([])
  })
})
