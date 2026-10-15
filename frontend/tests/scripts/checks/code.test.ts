import { describe, expect, it } from "vitest"
import { fileLength, MAX_LINES } from "../../../scripts/checks/rules/code/fileLength.ts"
import { importCycles } from "../../../scripts/checks/rules/code/importCycles.ts"
import { noComments } from "../../../scripts/checks/rules/code/noComments.ts"
import { packageSize, packageSubject } from "../../../scripts/checks/rules/code/packageShape.ts"
import { rawRequests } from "../../../scripts/checks/rules/code/requests.ts"
import { motionLibraries, uiKits } from "../../../scripts/checks/rules/code/stack.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text = "export const value = 1\n"): SourceFile => ({ path, text })
const lines = (count: number) => "x\n".repeat(count)
const manifest = (groups: Record<string, Record<string, string>>) =>
  file("package.json", JSON.stringify(groups))

describe("file-length", () => {
  it("passes a file at the limit and skips generated files", () => {
    expect(fileLength.run([file("src/a.ts", lines(MAX_LINES))])).toEqual([])
    expect(fileLength.run([file("src/shared/api/schema.gen.ts", lines(900))])).toEqual([])
  })

  it("weights a long file by its excess lines", () => {
    const [violation] = fileLength.run([file("src/a.css", lines(MAX_LINES + 7))])
    expect(violation).toMatchObject({ file: "src/a.css", weight: 7 })
  })
})

describe("no-comments", () => {
  it("passes code without comments and comment-like strings", () => {
    const code = file("src/a.ts", 'export const url = "http://x"\nexport const re = /\\/\\//\n')
    expect(noComments.run([code])).toEqual([])
  })

  it.each([
    ["src/a.ts", "// note\nexport const a = 1\n"],
    ["src/a.tsx", "export const A = () => <div>{/* note */}</div>\n"],
    ["src/a.css", ".a { color: var(--x); }\n/* note */\n"],
    ["index.html", "<div><!-- note --></div>\n"],
    ["tsconfig.json", '{\n  // note\n  "a": "//not"\n}\n'],
    ["nginx.conf", "server {\n    # note\n}\n"],
    ["Dockerfile", "# note\nFROM node\n"],
    ["index.html", "<script>\n// inline\n</script>\n"],
  ])("reports a comment in %s", (path, text) => {
    expect(noComments.run([file(path, text)])).toHaveLength(1)
  })

  it("allows biome-ignore and ts-expect-error with a reason", () => {
    const text = [
      "// biome-ignore lint/style/noX: needed for a reason",
      "export const a = 1",
      "// @ts-expect-error library type is wrong",
      "export const b = 2",
      "// biome-ignore lint/style/noX",
      "export const c = 3",
    ].join("\n")
    expect(noComments.run([file("src/a.ts", text)])).toHaveLength(1)
  })
})

describe("package-size and package-subject", () => {
  it("reports a folder with too many sources", () => {
    const sources = Array.from({ length: 21 }, (_, index) => file(`src/a/f${index}.ts`))
    expect(packageSize.run(sources).map((violation) => violation.file)).toEqual(["src/a"])
  })

  it.each([
    "src/utils/x.ts",
    "src/shared/helpers/x.ts",
    "src/features/x/lib/x.ts",
    "src/core/x.ts",
    "src/features/shared/x.ts",
    "tests/misc/x.ts",
  ])("reports %s", (path) => {
    expect(packageSubject.run([file(path)])).toHaveLength(1)
  })
})

describe("import-cycles", () => {
  it("passes an acyclic graph and type-only back edges", () => {
    const files = [
      file("src/a.ts", 'import { b } from "./b"\nexport const a = b\n'),
      file("src/b.ts", 'import type { A } from "@/a"\nexport const b = 1\n'),
    ]
    expect(importCycles.run(files)).toEqual([])
  })

  it("reports a runtime cycle through the alias and index files", () => {
    const files = [
      file("src/a.ts", 'import { b } from "@/feature"\nexport const a = b\n'),
      file("src/feature/index.ts", 'export { b } from "./b"\n'),
      file("src/feature/b.ts", 'import { a } from "../a"\nexport const b = a\n'),
    ]
    expect(importCycles.run(files)).toHaveLength(1)
  })
})

describe("raw-requests", () => {
  it("passes the api client inside query functions", () => {
    const text =
      'export const useOrders = () => useQuery({ queryKey: ["o"], queryFn: () => unwrap(api.GET("/api/orders")) })\n'
    const client = file("src/shared/api/client.ts", "export const x = fetch\nfetch('/x')\n")
    expect(rawRequests.run([file("src/entities/order/order.queries.ts", text), client])).toEqual([])
  })

  it("reports fetch, http libraries and requests inside effects", () => {
    const text = [
      'import axios from "axios"',
      'useEffect(() => { void api.GET("/api/orders") }, [])',
      'window.fetch("/api/x")',
    ].join("\n")
    const messages = rawRequests
      .run([file("src/features/orders/load.ts", text)])
      .map((item) => item.message)
    expect(messages).toEqual([
      "axios instead of the api client",
      "request inside an effect instead of TanStack Query",
      "fetch outside shared/api",
    ])
  })
})

describe("motion-libraries and ui-kits", () => {
  it("passes plain React dependencies", () => {
    const files = [manifest({ dependencies: { react: "19", clsx: "2" } })]
    expect([...motionLibraries.run(files), ...uiKits.run(files)]).toEqual([])
  })

  it("reports animation libraries and UI kits in every dependency group", () => {
    const files = [
      manifest({
        dependencies: { gsap: "3", "@radix-ui/react-dialog": "1" },
        devDependencies: { "framer-motion": "12", tailwindcss: "4" },
        peerDependencies: { "@mui/material": "7" },
      }),
    ]
    expect(motionLibraries.run(files)).toHaveLength(2)
    expect(uiKits.run(files)).toHaveLength(3)
  })
})
