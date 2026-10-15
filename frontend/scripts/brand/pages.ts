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

export function cardHtml(
  mark: string,
  text: CardText,
  colors: ThemePalette,
  fonts: string,
  family: string,
): string {
  const body = `<div id="asset" style="width:1200px;height:630px;display:grid;grid-template-rows:auto 1fr auto;padding:72px 88px;background:${colors.surface};color:${colors.base};-webkit-font-smoothing:antialiased">
  <div style="display:flex;align-items:center;gap:22px"><div style="width:72px;height:72px">${mark}</div><span style="font-size:44px;font-weight:650;letter-spacing:-0.02em">${escapeHtml(text.name)}</span></div>
  <div style="display:grid;align-content:center;gap:28px">
    <p style="font-size:68px;font-weight:700;line-height:1.05;letter-spacing:-0.035em;text-wrap:balance;max-width:1000px">${escapeHtml(text.tagline)}</p>
    <p style="font-size:30px;line-height:1.35;color:${colors.muted};max-width:960px;text-wrap:pretty">${escapeHtml(text.description)}</p>
  </div>
  <div style="display:flex;align-items:center;gap:20px;padding-top:28px;border-top:2px solid ${colors.line};font-size:26px;color:${colors.muted}"><span style="width:14px;height:14px;border-radius:50%;background:${colors.accent}"></span>${escapeHtml(text.site)}</div>
</div>`
  return page(body, `${fonts}#asset{font-family:${family}}`)
}
