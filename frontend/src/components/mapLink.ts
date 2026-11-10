// Genauer Punkt aus einem eingefügten Kartenlink (OpenStreetMap, Google Maps, geo:).

export interface Point {
  latitude: number
  longitude: number
}

function valid(lat: number, lon: number): Point | null {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { latitude: Math.round(lat * 1e5) / 1e5, longitude: Math.round(lon * 1e5) / 1e5 }
}

const NUM = '(-?\\d{1,3}(?:\\.\\d+)?)'
const PATTERNS = [
  // OSM: ?mlat=..&mlon=..
  new RegExp(`mlat=${NUM}.*?mlon=${NUM}`),
  // Google: !3d<lat>!4d<lon> (genauer als @)
  new RegExp(`!3d${NUM}!4d${NUM}`),
  // Google: @lat,lon,zoom
  new RegExp(`@${NUM},${NUM}`),
  // Google/Apple: q=, query=, ll=, destination=lat,lon
  new RegExp(`(?:[?&](?:q|query|ll|destination|daddr)=)${NUM}(?:,|%2C)\\s*${NUM}`, 'i'),
  // OSM: #map=zoom/lat/lon
  new RegExp(`#map=\\d+/${NUM}/${NUM}`),
  // geo:lat,lon
  new RegExp(`^geo:${NUM},${NUM}`, 'i'),
  // Nur Zahlen: „51.17, 6.75“
  new RegExp(`^\\s*${NUM}\\s*[,; ]\\s*${NUM}\\s*$`),
]

/** Breite und Länge aus einem Link oder „Breite, Länge“; null, wenn nichts passt. */
export function pointFromLink(text: string): Point | null {
  const value = text.trim()
  for (const re of PATTERNS) {
    const m = re.exec(value)
    if (m) return valid(Number(m[1]), Number(m[2]))
  }
  return null
}
