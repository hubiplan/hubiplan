// UX-Audit 16.11.2026, VW-13: Ohne das Modul Schießsport spricht das Modul Wettbewerbe nicht
// von Schützen, Schüssen, Ringen, Stechen oder Zügen.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SPORT_KEYS, sportText, useSportText } from '../pages/competitions/words.ts'

const SCHUETZENWORT = /Schütz|Schuss|Schüss|Schieß|Stechen|Ringe|Standmodus|am Stand|Zug/

describe('VW-13 Wörter der Wettbewerbe', () => {
  it('hat für jedes Schützenwort eine neutrale Fassung', () => {
    const neutral = sportText(false)
    const shooting = sportText(true)
    expect(SPORT_KEYS.length).toBeGreaterThan(30)
    for (const key of SPORT_KEYS) {
      expect(neutral(key), key).not.toMatch(SCHUETZENWORT)
      expect(shooting(key)).toBe(key)
    }
  })

  it('setzt Platzhalter in beiden Fassungen', () => {
    expect(sportText(false)('Die besten {n} Schüsse zählen.', { n: 3 })).toBe(
      'Die besten 3 Wertungen zählen.',
    )
    expect(sportText(true)('· {count} Schützen', { count: 12 })).toBe('· 12 Schützen')
  })

  it('bleibt ohne gewählte Einheit bei den Begriffen der Schützen', () => {
    function Probe() {
      return <p>{useSportText()('Schützen')}</p>
    }
    render(<Probe />)
    expect(screen.getByText('Schützen')).toBeInTheDocument()
  })
})
