// UX-Audit 08.11., dritte Web-Runde: W-12, W-17, W-20, X-04.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { CalendarView } from '../components/calendar/CalendarView.tsx'
import { categoryShorts } from '../components/calendar/categories.ts'
import { monthGrid, monthStart, today } from '../components/calendar/time.ts'
import { appPairLink } from '../components/appLink.ts'
import { PageNav } from '../components/ListControls.tsx'
import { contrastRatio } from '../theme/contrast.ts'
import { PAGE_BG } from '../theme/theme.ts'
import { BREAKPOINTS } from '../theme/breakpoints.ts'
import { occurrence } from './eventFixtures.ts'
import { fakeApi } from './fakeApi.ts'

const CSS = import.meta.glob(['../**/*.css'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const THEME = CSS['../theme/theme.css']

function token(name: string): string {
  const m = THEME.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))
  if (!m) throw new Error(name)
  return m[1]
}

describe('W-12 Kategorie im Monatskalender', () => {
  it('bildet eindeutige Kürzel', () => {
    const shorts = categoryShorts(['Versammlung', 'Geselliges', 'Versand', 'Übung'])
    expect(shorts.get('Geselliges')).toBe('Ges')
    expect(shorts.get('Übung')).toBe('Übu')
    expect(shorts.get('Versammlung')).not.toBe(shorts.get('Versand'))
    expect(shorts.get('Versammlung')).toBe('Versam')
    expect(shorts.get('Versand')).toBe('Versan')
  })

  it('nennt die Kategorie im Vorlesetext und in der Legende', async () => {
    const base = '/api/orgs/7/'
    const grid = monthGrid(monthStart(today()))
    fakeApi({
      [`GET ${base}events/?from=${grid[0]}&to=${grid[grid.length - 1]}`]: () => ({
        status: 200,
        body: {
          from: '',
          to: '',
          items: [occurrence()],
          can_manage: false,
          categories: [{ id: 3, name: 'Versammlung', color: '#2f5f8f', is_active: true }],
        },
      }),
    })
    localStorage.setItem('hubiplan.kalenderansicht', 'month')
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const item = await screen.findByRole('button', { name: /Jahreshauptversammlung · Versammlung/ })
    expect(item).toHaveAttribute('title', expect.stringContaining('Versammlung'))
    const legend = screen.getByRole('list', { name: 'Kategorien' })
    expect(within(legend).getByText('Versammlung')).toBeInTheDocument()
    expect(within(legend).getByText('Ver')).toBeInTheDocument()
  })
})

describe('W-17 Figur und Grund', () => {
  it('Karte hebt sich vom Seitengrund ab, Rand mindestens 1,5 : 1', () => {
    expect(token('--color-bg')).toBe(PAGE_BG)
    expect(contrastRatio('#ffffff', PAGE_BG)).toBeGreaterThanOrEqual(1.14)
    expect(contrastRatio('#ffffff', token('--color-card-border'))).toBeGreaterThanOrEqual(1.5)
  })

  it('Links, gedämpfter Text und Feldrahmen bleiben auf dem dunkleren Grund lesbar', () => {
    expect(contrastRatio(token('--color-link'), PAGE_BG)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(token('--color-text-muted'), PAGE_BG)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(token('--color-input-border'), PAGE_BG)).toBeGreaterThanOrEqual(3)
  })
})

describe('W-20 Bausteine', () => {
  it('Blättern über einen Baustein mit gleichem Wortlaut', () => {
    render(
      <PageNav prevDisabled nextDisabled={false} onPrev={() => {}} onNext={() => {}}>
        Seite 1 von 3
      </PageNav>,
    )
    expect(screen.getByRole('button', { name: 'Vorherige Seite' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Nächste Seite' })).toBeEnabled()
    expect(screen.getByText('Seite 1 von 3')).toBeInTheDocument()
  })

  it('CSS nutzt nur die drei Umbruchbreiten', () => {
    const allowed = new Set<string>(BREAKPOINTS)
    const found: string[] = []
    for (const [file, text] of Object.entries(CSS)) {
      for (const m of text.matchAll(/@media[^{]*?(?:min|max)-width:\s*([0-9.]+[a-z]+)/g)) {
        if (!allowed.has(m[1])) found.push(`${file}: ${m[1]}`)
      }
    }
    expect(found).toEqual([])
  })
})

describe('X-04 App auf demselben Telefon verbinden', () => {
  it('baut den App-Link aus der QR-Adresse', () => {
    expect(appPairLink('https://verein.example.de:8443/app/verbinden#code=Ab-_9')).toBe(
      'hubiplan://verbinden?server=https%3A%2F%2Fverein.example.de%3A8443&code=Ab-_9',
    )
    expect(appPairLink('https://verein.example.de/app/verbinden#code=abc')).toBe(
      'hubiplan://verbinden?server=https%3A%2F%2Fverein.example.de&code=abc',
    )
  })

  it('ohne Code oder ohne https kein Link', () => {
    expect(appPairLink('https://verein.example.de/app/verbinden')).toBeNull()
    expect(appPairLink('http://verein.example.de/app/verbinden#code=abc')).toBeNull()
    expect(appPairLink('kein Link')).toBeNull()
  })
})
