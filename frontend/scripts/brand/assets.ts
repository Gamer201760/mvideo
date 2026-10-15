export type Locale = "ru" | "en"

export interface RasterAsset {
  readonly file: string
  readonly size: number
  readonly kind: "tab" | "app" | "maskable"
}

export const META_LOCALE: Locale = "ru"

export const ICO_SIZES = [16, 32, 48] as const

export const RASTERS: readonly RasterAsset[] = [
  { file: "apple-touch-icon.png", size: 180, kind: "app" },
  { file: "icons/icon-192.png", size: 192, kind: "app" },
  { file: "icons/icon-512.png", size: 512, kind: "app" },
  { file: "icons/icon-maskable-512.png", size: 512, kind: "maskable" },
]

export const OG_SIZE = { width: 1200, height: 630 } as const

export const ogFile = (locale: Locale): string => `og/og-${locale}.png`

export const MANIFEST = "site.webmanifest"

export const REQUIRED_HEAD = [
  '<link rel="icon" href="/favicon.ico" sizes="32x32" />',
  '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />',
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />',
  '<link rel="manifest" href="/site.webmanifest" />',
  '<meta name="theme-color" content="%theme.light%" media="(prefers-color-scheme: light)" />',
  '<meta name="theme-color" content="%theme.dark%" media="(prefers-color-scheme: dark)" />',
  '<meta property="og:image" content="%meta.ogImage%" />',
  '<meta name="twitter:card" content="summary_large_image" />',
  "<title>%meta.title%</title>",
] as const
