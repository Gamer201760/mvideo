import { existsSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  ICO_SIZES,
  MANIFEST,
  OG_SIZE,
  ogFile,
  RASTERS,
  REQUIRED_HEAD,
} from "../../scripts/brand/assets.ts"
import { icoSizes, pngSize } from "../../scripts/brand/binary.ts"
import { faviconSvg, readMark, readPalette } from "../../scripts/brand/marks.ts"

const ROOT = process.cwd()
const PUBLIC = join(ROOT, "public")
const FIX = "run npm run brand:assets"

interface Manifest {
  readonly name: string
  readonly icons: readonly {
    readonly src: string
    readonly sizes: string
    readonly purpose: string
  }[]
}

describe("brand assets in public/", () => {
  it(`favicon.svg matches the current mark and tokens (${FIX})`, () => {
    const expected = faviconSvg(readMark(resolve(ROOT, "..")), readPalette(ROOT))
    expect(readFileSync(join(PUBLIC, "favicon.svg"), "utf8")).toBe(expected)
    expect(expected).toContain("prefers-color-scheme:dark")
  })

  it("favicon.ico carries 16, 32 and 48 px", () => {
    expect(icoSizes(readFileSync(join(PUBLIC, "favicon.ico")))).toEqual([...ICO_SIZES])
  })

  it.each(RASTERS.map((asset) => [asset.file, asset.size] as const))(
    "%s is %i px square",
    (file, size) => {
      expect(pngSize(readFileSync(join(PUBLIC, file)))).toEqual({ width: size, height: size })
    },
  )

  it.each(["ru", "en"] as const)("the %s social card is 1200 x 630", (locale) => {
    expect(pngSize(readFileSync(join(PUBLIC, ogFile(locale))))).toEqual(OG_SIZE)
  })

  it("the manifest points to real icons with the declared sizes, maskable included", () => {
    const manifest = JSON.parse(readFileSync(join(PUBLIC, MANIFEST), "utf8")) as Manifest
    expect(manifest.name).not.toBe("")
    expect(manifest.icons.some((icon) => icon.purpose === "maskable")).toBe(true)
    for (const icon of manifest.icons) {
      const file = join(PUBLIC, icon.src)
      expect(existsSync(file)).toBe(true)
      const size = pngSize(readFileSync(file))
      expect(`${size?.width}x${size?.height}`).toBe(icon.sizes)
    }
  })

  it("index.html links every icon, the manifest, the card and the title", () => {
    const html = readFileSync(join(ROOT, "index.html"), "utf8")
    for (const tag of REQUIRED_HEAD) expect(html).toContain(tag)
  })
})
