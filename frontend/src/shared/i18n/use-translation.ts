import { useTranslation as useNamespaces } from "react-i18next"
import { NAMESPACES } from "./resources"

export function useTranslation() {
  return useNamespaces(NAMESPACES)
}
