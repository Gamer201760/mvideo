import type { RasterAsset } from "./assets.ts"
import type { ThemePalette } from "./marks.ts"

export interface CardText {
  readonly name: string
  readonly tagline: string
  readonly description: string
  readonly site: string
}

const escapeHtml = (text: string): string =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")

const page = (body: string, fonts: string): string =>
  `<!doctype html><html><head><meta charset="utf-8"><style>${fonts}*{box-sizing:border-box;margin:0;padding:0}body{background:transparent}</style></head><body>${body}</body></html>`

export function tileHtml(
  mark: string,
  size: number,
  colors: ThemePalette,
  round: boolean,
  fill: number,
): string {
  const radius = round ? Math.round(size * 0.22) : 0
  const inner = Math.round(size * fill)
  return page(
    `<div id="asset" style="width:${size}px;height:${size}px;display:grid;place-items:center;background:${colors.raised};border-radius:${radius}px"><div style="width:${inner}px;height:${inner}px">${mark}</div></div>`,
    "",
  )
}

export function rasterHtml(mark: string, asset: RasterAsset, colors: ThemePalette): string {
  const fill = asset.kind === "maskable" ? 0.5 : 0.62
  return page(
    `<div id="asset" style="width:${asset.size}px;height:${asset.size}px;display:grid;place-items:center;background:${colors.surface}"><div style="width:${Math.round(asset.size * fill)}px;height:${Math.round(asset.size * fill)}px">${mark}</div></div>`,
    "",
  )
}

export interface CardArt {
  readonly mark: string
  readonly partner: string
  readonly prefix: string
  readonly value: string
  readonly quote: string
}

function wordmark(name: string, accent: string): string {
  const lower = escapeHtml(name.toLowerCase())
  const at = lower.lastIndexOf("i")
  if (at < 0) return lower
  return `${lower.slice(0, at)}<span style="position:relative;display:inline-block">ı<span style="position:absolute;left:50%;top:-0.02em;width:0.19em;height:0.19em;border-radius:50%;background:${accent};transform:translateX(-50%)"></span></span>${lower.slice(at + 1)}`
}

export function cardHtml(
  art: CardArt,
  text: CardText,
  light: ThemePalette,
  dark: ThemePalette,
  fonts: string,
  family: string,
): string {
  const body = `<div id="asset" style="position:relative;width:1200px;height:630px;display:grid;grid-template-rows:auto 1fr auto;padding:64px 80px;background:${light.shell};color:${dark.base};-webkit-font-smoothing:antialiased;overflow:hidden">
  <div style="display:flex;align-items:center;gap:18px">
    <div style="width:64px;height:59px">${art.mark}</div>
    <span style="font-size:52px;font-weight:800;letter-spacing:-0.045em;line-height:1">${wordmark(text.name, dark.accent)}</span>
    <span style="font-size:24px;font-weight:650;color:${dark.muted};margin-left:12px">${escapeHtml(art.prefix)}</span>
    <div style="height:26px;display:flex">${art.partner}</div>
  </div>
  <div style="display:grid;align-content:center;gap:24px;max-width:760px">
    <p style="font-size:64px;font-weight:800;line-height:1.02;letter-spacing:-0.04em;text-wrap:balance">${escapeHtml(text.tagline)}</p>
    <p style="font-size:26px;line-height:1.4;color:${dark.muted};text-wrap:pretty">${escapeHtml(text.description)}</p>
  </div>
  <div style="font-size:22px;font-weight:650;color:${dark.muted}">${text.site === "" ? "" : escapeHtml(text.site)}</div>
  <div style="position:absolute;right:88px;top:250px;display:grid;gap:120px;justify-items:end">
    <span style="font-family:ui-monospace,Consolas,monospace;font-size:24px;padding:8px 14px;border-radius:10px;background:${dark.raised};color:${dark.base}">${escapeHtml(art.quote)}</span>
    <span style="font-size:44px;font-weight:800;letter-spacing:-0.03em;padding:6px 18px;border-radius:14px;background:${dark.raised}">${escapeHtml(art.value)}</span>
  </div>
  <svg style="position:absolute;right:0;top:0" width="1200" height="630" viewBox="0 0 1200 630"><path d="M1134 272 C1172 272 1172 447 1134 447" fill="none" stroke="${dark.accent}" stroke-width="3" stroke-linecap="round"/><circle cx="1134" cy="272" r="6" fill="${dark.accent}"/><circle cx="1134" cy="447" r="6" fill="${dark.accent}"/></svg>
</div>`
  return page(body, `${fonts}#asset{font-family:${family}}`)
}
