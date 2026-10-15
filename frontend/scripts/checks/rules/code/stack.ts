import type { Check, SourceFile, Violation } from "../../types.ts"

const DEPENDENCY_GROUPS = [
  "dependencies",
  "devDependencies",
  "peerDependencies",
  "optionalDependencies",
]
const MOTION_PACKAGES = new Set([
  "framer-motion",
  "motion",
  "gsap",
  "animejs",
  "popmotion",
  "react-spring",
  "react-motion",
  "react-transition-group",
  "velocity-animate",
  "lottie-web",
  "lottie-react",
  "@formkit/auto-animate",
])
const MOTION_SCOPES = ["@motionone/", "@react-spring/", "@lottiefiles/", "@gsap/"]
const UI_KIT_PACKAGES = new Set([
  "tailwindcss",
  "antd",
  "bootstrap",
  "react-bootstrap",
  "daisyui",
  "shadcn",
  "styled-components",
  "@emotion/react",
  "@emotion/styled",
  "semantic-ui-react",
  "primereact",
])
const UI_KIT_SCOPES = [
  "@radix-ui/",
  "@mui/",
  "@chakra-ui/",
  "@mantine/",
  "@headlessui/",
  "@tailwindcss/",
  "@ark-ui/",
  "@heroui/",
  "@nextui-org/",
  "@shadcn/",
  "@base-ui-components/",
  "@fluentui/",
]

function installed(files: readonly SourceFile[]): [SourceFile, string[]] | null {
  const manifest = files.find((file) => file.path === "package.json")
  if (manifest === undefined) return null
  const parsed = JSON.parse(manifest.text) as Record<string, Record<string, string> | undefined>
  return [manifest, DEPENDENCY_GROUPS.flatMap((group) => Object.keys(parsed[group] ?? {}))]
}

function packageCheck(
  id: string,
  names: ReadonlySet<string>,
  scopes: readonly string[],
  kind: string,
): Check {
  return {
    id,
    run: (files) => {
      const found = installed(files)
      if (found === null) return []
      const [manifest, packages] = found
      return packages
        .filter((name) => names.has(name) || scopes.some((scope) => name.startsWith(scope)))
        .map((name): Violation => ({ file: manifest.path, message: `${name} is ${kind}` }))
    },
  }
}

export const motionLibraries = packageCheck(
  "motion-libraries",
  MOTION_PACKAGES,
  MOTION_SCOPES,
  "an animation library",
)

export const uiKits = packageCheck("ui-kits", UI_KIT_PACKAGES, UI_KIT_SCOPES, "a UI kit")
