// Zwischenüberschriften in der Seitenleiste (Ralf 18.11.): deutlich von Menüpunkten abgesetzt,
// mit Linie davor, kleinerer gedämpfter Schrift und ohne Zeiger oder Fläche beim Darüberfahren.
import { describe, expect, it } from 'vitest'
import { contrastRatio } from '../theme/contrast.ts'
import { sidebarMuted } from '../theme/theme.ts'

const stile = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const css = Object.entries(stile).find(([d]) => d.endsWith('/index.css'))![1]

function regel(selektor: string): string {
  const esc = selektor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const m = css.match(new RegExp(`(?:^|\\n)${esc}\\s*\\{([^}]*)\\}`))
  expect(m, `Regel ${selektor} fehlt`).not.toBeNull()
  return m![1]
}

describe('Zwischenüberschriften in der Seitenleiste', () => {
  it('haben eine Linie und Abstand davor, die erste nicht', () => {
    const r = regel('.sidebar-sub-heading')
    expect(r).toMatch(/border-top:\s*1px solid/)
    expect(r).toMatch(/margin-top:\s*0\.6rem/)
    expect(regel('.sidebar-sub-heading:first-child')).toMatch(/border-top:\s*0/)
  })

  it('sind kleiner als Unterpunkte und in der gedämpften Leistenfarbe', () => {
    const groesse = (r: string) => Number(r.match(/font-size:\s*([\d.]+)rem/)![1])
    expect(groesse(regel('.sidebar-sub-heading'))).toBeLessThan(groesse(regel('.sidebar-sublink')))
    expect(regel('.sidebar-sub-heading')).toMatch(/color:\s*var\(--sidebar-muted/)
  })

  it('wirken nicht anklickbar', () => {
    expect(regel('.sidebar-sub-heading')).toMatch(/cursor:\s*default/)
    expect(regel('.sidebar-sub-heading:hover')).toMatch(/background:\s*none/)
  })

  it('halten 4,5 : 1 auf verschiedenen Vereinsfarben', () => {
    for (const leiste of ['#0a5a4a', '#0b4a7d', '#1b1b1f', '#7a1020']) {
      expect(contrastRatio(sidebarMuted(leiste), leiste)).toBeGreaterThanOrEqual(4.5)
    }
  })
})
