import { describe, expect, it } from "vitest"
import { remoteAssets } from "../../../scripts/checks/rules/code/remoteAssets.ts"
import { globalStyles } from "../../../scripts/checks/rules/css/cssStructure.ts"
import { hoverGate } from "../../../scripts/checks/rules/css/hoverGate.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text: string): SourceFile => ({ path, text })
const module = (css: string) => file("src/shared/ui/box/styles.module.css", css)

describe("hover-gate", () => {
  it("passes hover inside the pointer media query and a static focus ring", () => {
    const css =
      "@media (hover: hover) and (pointer: fine) { .a:hover { color: var(--x); } }\n.a:focus-visible { outline: var(--ring); }\n.b { transition: var(--t); }\n.b:focus-visible { --thumb: var(--x); transition: none; }"
    expect(hoverGate.run([module(css)])).toEqual([])
  })

  it("reports bare hover and animated focus", () => {
    const css = ".a:hover { color: var(--x); }\n.a:focus-visible { transition: var(--t); }"
    expect(hoverGate.run([module(css)])).toHaveLength(2)
  })

  it("reports a focus change animated by the transition of its base class", () => {
    const css =
      ".ring { transition: var(--transition-control); }\n.ring:focus-visible { background-color: var(--surface-raised); }"
    expect(hoverGate.run([module(css)]).map((item) => item.message)).toEqual([
      ".ring:focus-visible change is animated by its base transition",
    ])
  })
})

describe("remote-assets", () => {
  it("passes local fonts, assets and SVG namespaces", () => {
    const css = '@font-face { src: url("/fonts/Inter-Regular.woff2"); }'
    const tsx = file(
      "src/shared/ui/mark/mark.tsx",
      'export const F = () => <svg xmlns="http://www.w3.org/2000/svg" />\n',
    )
    const html = file("index.html", '<script type="module" src="/src/main.tsx"></script>')
    expect(remoteAssets.run([module(css), tsx, html])).toEqual([])
  })

  it("reports CDN fonts, scripts, srcset and remote URLs in code", () => {
    const css = '@import "https://fonts.example.com/css2?family=Inter";'
    const html =
      '<link href="https://cdn.example.com/x.css">\n<script src="//cdn.example.com/a.js">\n<img srcset="https://cdn.example.com/a.png 2x" alt="x" />'
    const tsx = file(
      "src/features/x/index.tsx",
      'export const X = () => <img src="https://cdn.example.com/photo.png" alt="" />\nvoid new FontFace("p", "url(https://fonts.example.com/p.woff2)")\n',
    )
    expect(remoteAssets.run([module(css), file("index.html", html), tsx])).toHaveLength(6)
  })
})

describe("global-styles", () => {
  const global = file("src/shared/styles/global.css", ":root {}")
  const main = (body: string) => file("src/main.tsx", body)

  it("passes one import of global.css from the entry", () => {
    expect(globalStyles.run([global, main('import "./shared/styles/global.css"\n')])).toEqual([])
  })

  it("reports a missing entry import and imports from components", () => {
    const component = file(
      "src/features/x/index.tsx",
      'import "../../shared/styles/global.css"\nexport const X = 1\n',
    )
    expect(globalStyles.run([global, main("export {}\n"), component])).toHaveLength(2)
  })
})
