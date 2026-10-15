import { readFileSync } from "node:fs"
import { join } from "node:path"
import type { Plugin } from "vite"
import { META_LOCALE, ogFile } from "./brand/assets.ts"
import { readTokenSources, themeColor } from "./tokenSources.ts"

interface CommonWords {
  readonly app: { readonly name: string; readonly tagline: string }
  readonly meta: { readonly description: string }
}

const CANVAS_TOKEN = "--surface-base"

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;")
}

export function metaValues(frontendRoot: string): Readonly<Record<string, string>> {
  const localesDir = join(frontendRoot, "src", "shared", "i18n", "locales")
  const common = JSON.parse(
    readFileSync(join(localesDir, META_LOCALE, "common.json"), "utf8"),
  ) as CommonWords
  const tokens = readTokenSources(frontendRoot)
  const site = (process.env.SITE_URL ?? "").replace(/\/$/, "")
  return {
    "%meta.title%": [common.app.name, common.app.tagline].filter(Boolean).join(" | "),
    "%app.name%": common.app.name,
    "%meta.url%": `${site}/`,
    "%meta.ogImage%": `${site}/${ogFile(META_LOCALE)}`,
    "%meta.description%": common.meta.description,
    "%theme.light%": themeColor(tokens, "light", CANVAS_TOKEN) ?? "",
    "%theme.dark%": themeColor(tokens, "dark", CANVAS_TOKEN) ?? "",
  }
}

export function htmlMeta(frontendRoot: string): Plugin {
  return {
    name: "app-html-meta",
    transformIndexHtml(html) {
      return Object.entries(metaValues(frontendRoot)).reduce(
        (result, [token, value]) => result.replaceAll(token, escapeAttribute(value)),
        html,
      )
    },
  }
}
