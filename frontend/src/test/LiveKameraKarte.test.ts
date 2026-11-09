// Live-Kamera für die Karte mit fünf Spiegeln (Ralf 09.11.): an gezeichneten (erfundenen)
// Bildern prüfen, ob die Kamera alle fünf findet und nur bei passender Lage auslöst.
import { describe, expect, it } from 'vitest'
import { analyze, judgeCard } from '../pages/competitions/aim.ts'

const W = 160
const H = 120
// LG Kyffhäuser 5 Spiegel: Schwarz 29 mm, äußerster Ring (6) 38 mm
const SHARE = 29 / 38

/** Graubild: Tisch, weiße Karte, vier Spiegel in den Ecken und einer in der Mitte. */
function card({
  cx = 80,
  cy = 60,
  p = 34, // Abstand Eckspiegel zur Mitte je Achse (px)
  r = 10.4, // Radius des Schwarzen (px)
  half = 50, // halbe Kartenseite (px)
  squash = 1,
  light = 1,
  without = -1, // diesen Spiegel weglassen
  big = -1, // diesen Spiegel größer zeichnen
} = {}): Uint8Array {
  const centers: [number, number][] = [
    [0, 0],
    [-p, -p],
    [p, -p],
    [-p, p],
    [p, p],
  ]
  const g = new Uint8Array(W * H)
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const dx = x - cx
      const dy = (y - cy) / squash
      let v = 110 // Tisch
      if (Math.abs(dx) < half && Math.abs(dy) < half) v = 235 // Karte
      centers.forEach(([ox, oy], i) => {
        if (i === without) return
        const rr = i === big ? r * 1.6 : r
        const d = Math.hypot(dx - ox, dy - oy)
        if (d < rr) v = Math.abs(d - rr * 0.5) < 0.5 ? 200 : 25
      })
      g[y * W + x] = Math.min(255, v * light + ((x * 7 + y * 13) % 5))
    }
  }
  return g
}

const look = (opts: Parameters<typeof card>[0] = {}, prev?: Parameters<typeof card>[0]) =>
  judgeCard(analyze(card(opts), W, H), SHARE, prev ? analyze(card(prev), W, H) : null)

describe('Live-Kamera: Karte mit fünf Spiegeln', () => {
  it('findet alle fünf, Mitte zuerst, und löst bei ruhiger, gerader Karte aus', () => {
    const v = look({}, {})
    expect(v.ok).toBe(true)
    expect(v.found).toHaveLength(5)
    expect(Math.hypot(v.found[0].x, v.found[0].y)).toBeLessThan(0.02)
    // Eckspiegel 34 px auf 120 px Höhe von der Mitte
    for (const q of v.found.slice(1)) {
      expect(Math.abs(Math.abs(q.x) - 34 / 120)).toBeLessThan(0.03)
      expect(Math.abs(Math.abs(q.y) - 34 / 120)).toBeLessThan(0.03)
    }
  })

  it('braucht keine festen Kartenmaße: auch engere Anordnung geht', () => {
    expect(look({ p: 28, half: 44 }).ok).toBe(true)
  })

  it('gibt Hinweise, was zu ändern ist', () => {
    expect(look({ without: 3 }).hint).toMatch(/4 von 5 Spiegeln/)
    expect(look({ p: 14, r: 4.5, half: 22 }).hint).toMatch(/Näher heran/)
    expect(look({ p: 44, r: 13, half: 59 }).hint).toMatch(/weiter weg/)
    expect(look({ cx: 70 }).hint).toMatch(/Mitte/)
    expect(look({ squash: 0.8 }).hint).toMatch(/Gerade von oben/)
    expect(look({ big: 0 }).hint).toMatch(/Gerade von oben/)
    expect(look({ light: 0.15 }).hint).toMatch(/Zu dunkel/)
    expect(look({}, { cx: 84 }).hint).toMatch(/Ruhig halten/)
  })
})
