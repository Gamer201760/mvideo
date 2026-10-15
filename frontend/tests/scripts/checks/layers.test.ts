import { describe, expect, it } from "vitest"
import { layerOf, layers } from "../../../scripts/checks/rules/code/layers.ts"
import type { SourceFile } from "../../../scripts/checks/types.ts"

const file = (path: string, text = "export const value = 1\n"): SourceFile => ({ path, text })
const importing = (path: string, specifier: string) =>
  file(path, `import { value } from "${specifier}"\nexport const used = value\n`)

const TARGETS = [
  file("src/shared/ui/index.ts"),
  file("src/entities/order/order-row/order-row.tsx"),
  file("src/entities/user/user-badge/user-badge.tsx"),
  file("src/features/cart/cart-line/cart-line.tsx"),
  file("src/features/checkout/checkout-dialog/checkout-dialog.tsx"),
  file("src/pages/orders/orders-page.tsx"),
  file("src/app/root-layout/root-layout.tsx"),
]

describe("layers", () => {
  it("names the layer of a path", () => {
    expect(
      ["src/shared/a.ts", "src/entities/x/a.ts", "src/features/x/a.ts", "src/main.tsx"].map(
        layerOf,
      ),
    ).toEqual(["shared", "entities", "features", "root"])
  })

  it("passes dependencies that point down", () => {
    const files = [
      ...TARGETS,
      importing("src/entities/order/a.ts", "@/shared/ui"),
      importing("src/features/cart/a.ts", "@/entities/user/user-badge/user-badge"),
      importing("src/features/cart/b.ts", "./cart-line/cart-line"),
      importing("src/pages/orders/a.ts", "@/features/checkout/checkout-dialog/checkout-dialog"),
      importing("src/app/a.ts", "@/pages/orders/orders-page"),
      importing("src/features/cart/c.tsx", "react"),
      importing("src/main.tsx", "./app/root-layout/root-layout"),
    ]
    expect(layers.run(files)).toEqual([])
  })

  it.each([
    ["src/shared/ui/probe.tsx", "@/entities/user/user-badge/user-badge"],
    ["src/shared/ui/probe.tsx", "@/app/root-layout/root-layout"],
    ["src/entities/order/probe.ts", "@/features/cart/cart-line/cart-line"],
    ["src/entities/order/probe.ts", "@/entities/user/user-badge/user-badge"],
    ["src/features/cart/probe.ts", "@/features/checkout/checkout-dialog/checkout-dialog"],
    ["src/features/cart/probe.ts", "@/pages/orders/orders-page"],
    ["src/pages/orders/probe.ts", "@/app/root-layout/root-layout"],
  ])("reports %s importing %s", (path, specifier) => {
    expect(layers.run([...TARGETS, importing(path, specifier)])).toHaveLength(1)
  })
})
