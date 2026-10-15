import {
  Check,
  ChevronDown,
  CircleCheck,
  CircleHelp,
  FileText,
  House,
  Inbox,
  ListChecks,
  LoaderCircle,
  type LucideProps,
  Moon,
  PencilLine,
  RefreshCw,
  RotateCcw,
  ScanText,
  Sun,
  TriangleAlert,
} from "lucide-react"
import type { ComponentType } from "react"

export const ICONS = {
  alert: TriangleAlert,
  check: Check,
  "chevron-down": ChevronDown,
  card: FileText,
  extract: ScanText,
  review: ListChecks,
  correct: PencilLine,
  unknown: CircleHelp,
  success: CircleCheck,
  empty: Inbox,
  home: House,
  loader: LoaderCircle,
  refresh: RefreshCw,
  retry: RotateCcw,
  "theme-light": Sun,
  "theme-dark": Moon,
} as const satisfies Record<string, ComponentType<LucideProps>>

export type IconName = keyof typeof ICONS
