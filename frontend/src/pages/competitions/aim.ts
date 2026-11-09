import { t } from '../../i18n/index.ts'
// Live-Kamera (Schießscheiben Schritt 5): ein kleines Graubild je Kamerabild prüfen und
// sagen, ob die Scheibe gut im Bild ist. Nur grob und schnell (etwa 160 Bildpunkte breit);
// die genaue Auswertung macht danach der Server mit dem vollen Foto.

export interface Spot {
  /** Mitte des Spiegels, 0–1 je Achse */
  cx: number
  cy: number
  /** Durchmesser des Spiegels im Verhältnis zur kürzeren Bildseite */
  size: number
  /** kleine / große Achse: 1 = Kamera genau senkrecht über der Scheibe */
  round: number
}

export interface Frame {
  spot: Spot | null
  /** alle runden dunklen Flächen (Karten mit mehreren Spiegeln), größte zuerst */
  spots: Spot[]
  /** Breite / Höhe des Bilds */
  aspect: number
  /** mittlere Helligkeit 0–255 */
  light: number
  /** Schärfe (mittlerer Betrag des Laplace-Filters); höher ist schärfer */
  sharp: number
}

/** RGBA-Bild in ein Graubild umrechnen. */
export function toGray(rgba: Uint8ClampedArray, w: number, h: number): Uint8Array {
  const out = new Uint8Array(w * h)
  for (let i = 0, j = 0; j < out.length; i += 4, j++) {
    out[j] = (rgba[i] * 77 + rgba[i + 1] * 150 + rgba[i + 2] * 29) >> 8
  }
  return out
}

function otsu(gray: Uint8Array): number {
  const hist = new Array<number>(256).fill(0)
  for (const v of gray) hist[v]++
  const total = gray.length
  let sum = 0
  for (let i = 0; i < 256; i++) sum += i * hist[i]
  let sumB = 0
  let wB = 0
  let best = 0
  let level = 127
  for (let tm = 0; tm < 256; tm++) {
    wB += hist[tm]
    if (!wB) continue
    const wF = total - wB
    if (!wF) break
    sumB += tm * hist[tm]
    const mB = sumB / wB
    const mF = (sum - sumB) / wF
    const between = wB * wF * (mB - mF) ** 2
    if (between > best) {
      best = between
      level = tm
    }
  }
  return level
}

/** Dunkelste runde Fläche, die nicht am Bildrand liegt: der Spiegel. */
export function findSpot(gray: Uint8Array, w: number, h: number): Spot | null {
  return findSpots(gray, w, h)[0] ?? null
}

/**
 * Alle dunklen, runden Flächen, die nicht am Bildrand liegen, die größte (mal Rundheit)
 * zuerst. Bei Karten mit mehreren Spiegeln ist jede davon ein Spiegel.
 */
export function findSpots(gray: Uint8Array, w: number, h: number): Spot[] {
  const level = otsu(gray)
  const seen = new Uint8Array(w * h)
  const stack = new Int32Array(w * h)
  const found: (Spot & { score: number })[] = []
  for (let start = 0; start < w * h; start++) {
    if (seen[start] || gray[start] >= level) continue
    // Fläche füllen und dabei die Momente sammeln
    let n = 0
    let sx = 0
    let sy = 0
    let sxx = 0
    let syy = 0
    let sxy = 0
    let edge = false
    let top = 0
    stack[top++] = start
    seen[start] = 1
    while (top) {
      const p = stack[--top]
      const x = p % w
      const y = (p - x) / w
      n++
      sx += x
      sy += y
      sxx += x * x
      syy += y * y
      sxy += x * y
      if (x === 0 || y === 0 || x === w - 1 || y === h - 1) edge = true
      const next = [p - 1, p + 1, p - w, p + w]
      for (let k = 0; k < 4; k++) {
        const q = next[k]
        if (q < 0 || q >= w * h || seen[q] || gray[q] >= level) continue
        if (k < 2 && Math.abs((q % w) - x) !== 1) continue // nicht über den Zeilenrand
        seen[q] = 1
        stack[top++] = q
      }
    }
    if (edge || n < 0.004 * w * h) continue
    const mx = sx / n
    const my = sy / n
    const cxx = sxx / n - mx * mx
    const cyy = syy / n - my * my
    const cxy = sxy / n - mx * my
    // Achsen der Ellipse mit gleichen Momenten
    const tr = cxx + cyy
    const det = cxx * cyy - cxy * cxy
    const disc = Math.sqrt(Math.max(0, (tr * tr) / 4 - det))
    const l1 = tr / 2 + disc
    const l2 = tr / 2 - disc
    if (l2 <= 0) continue
    const a = 2 * Math.sqrt(l1)
    const b = 2 * Math.sqrt(l2)
    const fill = n / (Math.PI * a * b) // 1 für eine volle Ellipse
    const round = b / a
    if (fill < 0.75 || fill > 1.25 || round < 0.5) continue
    found.push({
      cx: mx / w,
      cy: my / h,
      size: (2 * Math.sqrt(a * b)) / Math.min(w, h),
      round,
      score: n * round,
    })
  }
  return found
    .sort((x, y) => y.score - x.score)
    .map(({ score: _score, ...spot }) => {
      void _score
      return spot
    })
}

/** Schärfe: mittlerer Betrag des Laplace-Filters (Kanten scharf = groß). */
export function sharpness(gray: Uint8Array, w: number, h: number): number {
  let sum = 0
  let n = 0
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x
      sum += Math.abs(4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w])
      n++
    }
  }
  return n ? sum / n : 0
}

/** Weichzeichnen (zweimal 3×3-Mittel), damit helle Ringlinien im Spiegel ihn nicht zerteilen. */
export function soften(gray: Uint8Array, w: number, h: number): Uint8Array {
  let src = gray
  for (let pass = 0; pass < 2; pass++) {
    const out = new Uint8Array(w * h)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let sum = 0
        let n = 0
        for (let dy = -1; dy <= 1; dy++) {
          const yy = y + dy
          if (yy < 0 || yy >= h) continue
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx
            if (xx < 0 || xx >= w) continue
            sum += src[yy * w + xx]
            n++
          }
        }
        out[y * w + x] = sum / n
      }
    }
    src = out
  }
  return src
}

export function analyze(gray: Uint8Array, w: number, h: number): Frame {
  let light = 0
  for (const v of gray) light += v
  const spots = findSpots(soften(gray, w, h), w, h)
  return {
    spot: spots[0] ?? null,
    spots,
    aspect: h ? w / h : 1,
    light: gray.length ? light / gray.length : 0,
    sharp: sharpness(gray, w, h),
  }
}

export interface Aim {
  ok: boolean
  hint: string
}

/**
 * Ist das Bild gut genug zum Auslösen? ``blackShare``: Durchmesser des Spiegels geteilt
 * durch den äußersten Ring (die ganze Scheibe soll ins Bild, aber möglichst groß).
 */
export function judge(f: Frame, blackShare: number, prev?: Frame | null): Aim {
  if (f.light < 50) return { ok: false, hint: t('Zu dunkel – bitte mehr Licht.') }
  const s = f.spot
  if (!s) return { ok: false, hint: t('Scheibe nicht gefunden – den Spiegel ins Bild halten.') }
  const whole = s.size / blackShare // äußerster Ring im Verhältnis zur kürzeren Bildseite
  if (whole > 0.95) return { ok: false, hint: t('Etwas weiter weg – die ganze Scheibe ins Bild.') }
  if (whole < 0.6) return { ok: false, hint: t('Näher heran.') }
  if (Math.hypot(s.cx - 0.5, s.cy - 0.5) > 0.12) {
    return { ok: false, hint: t('Scheibe in die Mitte des Bildes.') }
  }
  if (s.round < 0.93) return { ok: false, hint: t('Gerade von oben halten, nicht schräg.') }
  if (prev?.spot) {
    const moved = Math.hypot(s.cx - prev.spot.cx, s.cy - prev.spot.cy)
    if (moved > 0.01 || Math.abs(s.size - prev.spot.size) > 0.02) {
      return { ok: false, hint: t('Ruhig halten …') }
    }
  }
  if (f.sharp < 2) return { ok: false, hint: t('Unscharf – ruhig halten.') }
  return { ok: true, hint: t('Gut so – gleich wird ausgelöst.') }
}

/** Lage eines Spiegels im quadratischen Ausschnitt, Einheit: Seite des Ausschnitts, Mitte = 0. */
export interface Placed {
  x: number
  y: number
  /** Durchmesser des Schwarzen */
  size: number
  round: number
}

/** Spiegel in den sichtbaren quadratischen Ausschnitt umrechnen (das Kamerabild wird mittig zugeschnitten). */
export function placeSpots(f: Frame): Placed[] {
  const wide = f.aspect >= 1
  return f.spots.map((s) => ({
    x: (s.cx - 0.5) * (wide ? f.aspect : 1),
    y: (s.cy - 0.5) * (wide ? 1 : 1 / f.aspect),
    size: s.size,
    round: s.round,
  }))
}

export interface CardAim extends Aim {
  /** erkannte Spiegel im Ausschnitt (zum Einzeichnen), Mitte zuerst */
  found: Placed[]
}

/**
 * Karte mit fünf Spiegeln (vier Ecken und Mitte, Ralf 09.11.): Die Kartenmaße sind nicht
 * genormt, deshalb prüft die Kamera nur die Form. Fünf etwa gleich große, runde Spiegel,
 * einer in der Mitte, vier rundherum in gleichem Abstand und im rechten Winkel zueinander;
 * alles ganz im Bild, groß genug und ruhig. Die genaue Lage misst danach der Server.
 */
export function judgeCard(f: Frame, blackShare: number, prev?: Frame | null): CardAim {
  const placed = placeSpots(f).slice(0, 7)
  const no = (hint: string, found: Placed[] = placed): CardAim => ({ ok: false, hint, found })
  if (f.light < 50) return no(t('Zu dunkel – bitte mehr Licht.'), [])
  if (placed.length < 5) {
    return no(
      placed.length
        ? t('{n} von 5 Spiegeln gefunden – die ganze Karte ins Bild.', { n: placed.length })
        : t('Scheibe nicht gefunden – den Spiegel ins Bild halten.'),
    )
  }
  // die fünf, deren Größe am besten zusammenpasst
  let five = placed.slice(0, 5)
  let spread = Infinity
  const bySize = [...placed].sort((a, b) => b.size - a.size)
  for (let i = 0; i + 5 <= bySize.length; i++) {
    const g = bySize.slice(i, i + 5)
    const sp = g[0].size / g[4].size
    if (sp < spread) {
      spread = sp
      five = g
    }
  }
  // Mitte: der Spiegel, der dem Schwerpunkt der fünf am nächsten liegt
  const mx = five.reduce((a, p) => a + p.x, 0) / 5
  const my = five.reduce((a, p) => a + p.y, 0) / 5
  const mid = five.reduce((a, p) =>
    Math.hypot(p.x - mx, p.y - my) < Math.hypot(a.x - mx, a.y - my) ? p : a,
  )
  const ring = five.filter((p) => p !== mid)
  const found = [mid, ...ring]
  const dist = ring.map((p) => Math.hypot(p.x - mid.x, p.y - mid.y))
  const dMin = Math.min(...dist)
  const dMax = Math.max(...dist)
  const angles = ring.map((p) => Math.atan2(p.y - mid.y, p.x - mid.x)).sort((a, b) => a - b)
  const gaps = angles.map((a, i) => (i < 3 ? angles[i + 1] - a : angles[0] + 2 * Math.PI - a))
  const square = gaps.every((g) => Math.abs(g - Math.PI / 2) < 0.35)
  if (spread > 1.35 || dMin < 0.8 * dMax || !square || dMin < mid.size) {
    // ungleich große Spiegel oder schiefes X: meist schräg gehalten
    if (spread > 1.35 || dMin < 0.8 * dMax)
      return no(t('Gerade von oben halten, nicht schräg.'), found)
    return no(t('Karte nicht erkannt – vier Spiegel in den Ecken und einer in der Mitte.'), found)
  }
  if (found.some((p) => p.round < 0.9)) return no(t('Gerade von oben halten, nicht schräg.'), found)
  if (Math.hypot(mid.x, mid.y) > 0.08) return no(t('Karte in die Mitte des Bildes.'), found)
  // äußerster Ring der Eckspiegel muss ganz im Ausschnitt liegen
  const outer = (p: Placed) => p.size / blackShare / 2
  const reach = Math.max(...ring.map((p) => Math.max(Math.abs(p.x), Math.abs(p.y)) + outer(p)))
  if (reach > 0.48) return no(t('Etwas weiter weg – die ganze Karte ins Bild.'), found)
  if (dMax + outer(ring[0]) < 0.3) return no(t('Näher heran.'), found)
  if (prev) {
    const before = cardMid(prev)
    if (
      !before ||
      Math.hypot(before.x - mid.x, before.y - mid.y) > 0.01 ||
      Math.abs(before.size - mid.size) > 0.02
    ) {
      return no(t('Ruhig halten …'), found)
    }
  }
  if (f.sharp < 2) return no(t('Unscharf – ruhig halten.'), found)
  return { ok: true, hint: t('Gut so – gleich wird ausgelöst.'), found }
}

/** Mittlerer Spiegel eines früheren Bilds (für „ruhig halten“): der zur Bildmitte nächste. */
function cardMid(f: Frame): Placed | null {
  const placed = placeSpots(f)
  if (placed.length < 5) return null
  return placed.reduce((a, p) => (Math.hypot(p.x, p.y) < Math.hypot(a.x, a.y) ? p : a))
}

/** Kann der Browser die Kamera live zeigen (nur über HTTPS bzw. localhost)? */
export function cameraAvailable(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}
