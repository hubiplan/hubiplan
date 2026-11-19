// Schriftkontrast (Ralf 19.11.2026, Dialog „Deine Anmeldung ist abgelaufen“): Die kleine
// Erklärung unter der Beschriftung eines gefüllten Knopfs stand grau auf Vereinsfarbe und war
// kaum lesbar. In gefüllten Knöpfen übernimmt sie die Schriftfarbe des Knopfs, die das Design
// für ausreichenden Kontrast berechnet (--color-on-button-primary, Weiß bei Löschen).
import { describe, expect, it } from 'vitest'
import css from '../index.css?raw'

function regelnFuer(klasse: string): string[] {
  const regeln: string[] = []
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (m[1].includes(klasse)) regeln.push(`${m[1].trim()} {${m[2]}}`)
  }
  return regeln
}

describe('Erklärung in gefüllten Knöpfen', () => {
  const regeln = regelnFuer('.choice-hint')

  it.each(['.button-primary .choice-hint', '.button-danger-solid .choice-hint'])(
    '%s übernimmt die Schriftfarbe des Knopfs',
    (selektor) => {
      const regel = regeln.find((r) => r.includes(selektor))
      expect(regel, selektor).toBeDefined()
      expect(regel).toMatch(/color:\s*inherit/)
    },
  )

  it('ausgewählte Knöpfe (aria-pressed, aktiv) ebenso', () => {
    const regel = regeln.find(
      (r) => r.includes("[aria-pressed='true']") && r.includes('.choice-hint'),
    )
    expect(regel).toMatch(/color:\s*inherit/)
  })

  it('kein anderer Text mit gedämpfter Farbe steht in einem gefüllten Knopf', () => {
    // Gegenprobe: keine Regel setzt grauen Text gezielt in gefüllte Knöpfe
    for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const sel = m[1]
      if (/\.button-primary\s+\S|\.button-danger-solid\s+\S/.test(sel)) {
        expect(m[2], sel.trim()).not.toMatch(/color:\s*var\(--color-text-muted\)/)
      }
    }
  })
})
