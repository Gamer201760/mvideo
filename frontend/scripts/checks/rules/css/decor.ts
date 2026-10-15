import { parseStyles } from "../../parse.ts"
import { type Check, isSource, isStyle, type Violation } from "../../types.ts"

const GRADIENT = /(?:repeating-)?(?:linear|radial|conic)-gradient\(/
const MASK_PROPERTY = /^(-webkit-)?mask(-image)?$/

export function decorProblem(prop: string, value: string): string | null {
  if (prop.endsWith("background-clip") && value.includes("text")) return "gradient text"
  if (GRADIENT.test(value) && !MASK_PROPERTY.test(prop)) return "gradient"
  return null
}

export const noGradients: Check = {
  id: "no-gradients",
  run: (files) =>
    files
      .filter((file) => isSource(file.path) && isStyle(file.path))
      .flatMap((file) => {
        const found: Violation[] = []
        parseStyles(file.text).walkDecls((declaration) => {
          const problem = decorProblem(declaration.prop, declaration.value)
          if (problem !== null)
            found.push({
              file: file.path,
              message: `${problem}: ${declaration.prop}: ${declaration.value}`,
            })
        })
        return found
      }),
}
