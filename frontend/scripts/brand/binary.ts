export interface PngImage {
  readonly size: number
  readonly data: Buffer
}

const PNG_SIGNATURE = "89504e470d0a1a0a"

export function pngSize(data: Buffer): { readonly width: number; readonly height: number } | null {
  if (data.length < 24 || data.subarray(0, 8).toString("hex") !== PNG_SIGNATURE) return null
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) }
}

export function buildIco(images: readonly PngImage[]): Buffer {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(images.length, 4)
  let offset = 6 + images.length * 16
  const entries = images.map((image) => {
    const entry = Buffer.alloc(16)
    entry.writeUInt8(image.size >= 256 ? 0 : image.size, 0)
    entry.writeUInt8(image.size >= 256 ? 0 : image.size, 1)
    entry.writeUInt8(0, 2)
    entry.writeUInt8(0, 3)
    entry.writeUInt16LE(1, 4)
    entry.writeUInt16LE(32, 6)
    entry.writeUInt32LE(image.data.length, 8)
    entry.writeUInt32LE(offset, 12)
    offset += image.data.length
    return entry
  })
  return Buffer.concat([header, ...entries, ...images.map((image) => image.data)])
}

export function icoSizes(data: Buffer): number[] {
  if (data.length < 6 || data.readUInt16LE(2) !== 1) return []
  const count = data.readUInt16LE(4)
  return Array.from({ length: count }, (_, index) => data.readUInt8(6 + index * 16) || 256)
}
