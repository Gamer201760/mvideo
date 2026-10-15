export const TITLE_SEPARATOR = " | "

export function documentTitle(app: string, tagline: string, page: string | null): string {
  const parts = page === null ? [app, tagline] : [page, app]
  return parts.filter((part) => part.trim() !== "").join(TITLE_SEPARATOR)
}
