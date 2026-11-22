// Seiten der Verwaltung stehen links an der Inhaltskante, nicht mittig
// (Belegung und Material waren zentriert, alle anderen Seiten links).
import { describe, expect, it } from 'vitest'

const SEITEN_CSS = import.meta.glob('../pages/**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// Eigenständige Ansichten ohne Seitenleiste dürfen mittig stehen.
const AUSNAHMEN = new Set(['music-guest-page'])

function mittigeSeiten(css: string): string[] {
  const treffer: string[] = []
  for (const m of css.matchAll(/^\.([\w-]+)\s*\{([^}]*)\}/gm)) {
    const [, klasse, rumpf] = m
    if (AUSNAHMEN.has(klasse)) continue
    if (/max-width/.test(rumpf) && /margin(-inline)?:\s*0?\s*auto/.test(rumpf)) {
      treffer.push(klasse)
    }
  }
  return treffer
}

describe('Seitenlayout', () => {
  it('kein Seitencontainer ist mittig zentriert', () => {
    const gefunden = Object.entries(SEITEN_CSS).flatMap(([datei, css]) =>
      mittigeSeiten(css).map((k) => `${datei}: .${k}`),
    )
    expect(gefunden).toEqual([])
  })

  it('erkennt einen mittigen Container', () => {
    expect(mittigeSeiten('.x {\n  max-width: 10rem;\n  margin: 0 auto;\n}')).toEqual(['x'])
  })
})
