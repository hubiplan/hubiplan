// UX-Audit 16.11.2026, mittlere Befunde der Verwaltung:
// VW-05 Rückfragen nennen die Handlung, Rot nur bei Löschen und Trennen.
// VW-10 Die Kein-Zugriff-Karte bietet den Wechsel in die passende Einheit an; Links tragen sie.
// VW-43 Eingeblendete Formulare schließen mit Escape.
// VW-59 Die Schnellsuche findet Termine.
import { readFileSync } from 'node:fs'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import type { Occurrence } from '../api/events.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { confirmDialog } from '../components/dialog.ts'
import { QuickSearch } from '../components/QuickSearch.tsx'
import { matchEvents } from '../components/quickSearchEvents.ts'
import { useRevealFocus } from '../components/revealFocus.ts'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

describe('VW-05 Rückfragen', () => {
  it('hat keinen festen deutschen Knopftext mehr', () => {
    const source = readFileSync('src/components/AppDialog.tsx', 'utf8')
    expect(source).not.toMatch(/'Ja'/)
    expect(source).not.toMatch(/\?\? 'OK'/)
  })

  it('zeigt Rot nur, wenn die Frage nicht als harmlos gekennzeichnet ist', async () => {
    const user = userEvent.setup()
    const harmless = confirmDialog({
      message: 'Jetzt abgleichen?',
      confirmLabel: 'Jetzt abgleichen',
      danger: false,
    })
    const sync = screen.getByRole('button', { name: 'Jetzt abgleichen' })
    expect(sync.className).not.toMatch(/danger/)
    await user.click(sync)
    await expect(harmless).resolves.toBe(true)

    const destructive = confirmDialog({
      message: 'Foto löschen?',
      confirmLabel: 'Löschen',
      final: false,
    })
    const remove = screen.getByRole('button', { name: 'Löschen' })
    expect(remove.className).toMatch(/danger/)
    await user.click(remove)
    await expect(destructive).resolves.toBe(true)
  })
})

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

function Ort() {
  const { pathname, search } = useLocation()
  return <p data-testid="ort">{pathname + search}</p>
}

describe('VW-10 Kein Zugriff', () => {
  afterEach(() => {
    localStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  const OHNE = testOrg({ id: 7, name: 'Jägerzug', permissions: ['events.view'] })
  const MIT = testOrg({ id: 8, name: 'SV Musterstadt', permissions: ['members.view'] })

  function renderAt(path: string) {
    const api = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [OHNE, MIT] }),
    })
    render(
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    return api
  }

  it('bietet den Wechsel in die Einheit mit dem nötigen Recht an', async () => {
    const api = renderAt('/mitglieder')
    const card = await screen.findByTestId('kein-zugriff')
    expect(within(card).getByText(/Aktuell gewählt: Jägerzug/)).toBeInTheDocument()
    expect(within(card).getByText('In diesen Einheiten darfst du die Seite öffnen:')).toBeVisible()
    fireEvent.click(within(card).getByRole('button', { name: 'Weiter in SV Musterstadt' }))
    await waitFor(() => expect(screen.queryByTestId('kein-zugriff')).not.toBeInTheDocument())
    await waitFor(() =>
      expect(api.some((c) => c.key.startsWith('GET /api/orgs/8/members/'))).toBe(true),
    )
  })

  it('bleibt ohne passende Einheit beim Hinweis und der Startseite', async () => {
    renderAt('/webseite')
    const card = await screen.findByTestId('kein-zugriff')
    expect(within(card).queryByRole('button', { name: /Weiter in/ })).not.toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Zur Startseite' })).toBeInTheDocument()
  })

  it('wählt die Einheit aus dem Link (?einheit=) und nimmt die Angabe aus der Adresse', async () => {
    window.history.replaceState(null, '', '/mitglieder?einheit=8')
    const api = renderAt('/mitglieder')
    await waitFor(() =>
      expect(api.some((c) => c.key.startsWith('GET /api/orgs/8/members/'))).toBe(true),
    )
    expect(screen.queryByTestId('kein-zugriff')).not.toBeInTheDocument()
    expect(window.location.search).toBe('')
  })

  it('übergeht eine fremde Einheit im Link', async () => {
    window.history.replaceState(null, '', '/mitglieder?einheit=99')
    renderAt('/mitglieder')
    expect(await screen.findByTestId('kein-zugriff')).toBeInTheDocument()
    // Der Hinweis kann erscheinen, bevor die Angabe aus der Adresse genommen ist
    await waitFor(() => expect(window.location.search).toBe(''))
  })
})

describe('VW-43 Eingeblendetes Formular', () => {
  function Formular({ onEscape }: { onEscape: () => void }) {
    const ref = useRevealFocus<HTMLFormElement>(true, onEscape)
    return (
      <form ref={ref}>
        <input aria-label="Name" />
        <button type="button" aria-expanded="true">
          Auswahl
        </button>
      </form>
    )
  }

  it('bekommt den Fokus und schließt mit Escape, offene Auswahllisten zuerst', async () => {
    const user = userEvent.setup()
    const onEscape = vi.fn()
    render(<Formular onEscape={onEscape} />)
    expect(screen.getByLabelText('Name')).toHaveFocus()
    screen.getByRole('button', { name: 'Auswahl' }).focus()
    await user.keyboard('{Escape}')
    expect(onEscape).not.toHaveBeenCalled()
    screen.getByLabelText('Name').focus()
    await user.keyboard('{Escape}')
    expect(onEscape).toHaveBeenCalledTimes(1)
  })
})

const termin = (id: number, title: string, starts_at: string): Occurrence =>
  ({ key: `${id}-${starts_at}`, event_id: id, title, starts_at }) as Occurrence

describe('VW-59 Schnellsuche findet Termine', () => {
  const ITEMS = [
    termin(1, 'Generalversammlung', '2026-03-06T18:00:00Z'),
    termin(2, 'Zugabend', '2026-11-20T19:00:00Z'),
    termin(2, 'Zugabend', '2026-12-18T19:00:00Z'),
    termin(3, 'Außerordentliche Versammlung', '2027-01-15T18:00:00Z'),
    termin(4, 'Versammlung der Jugend', '2026-10-30T18:00:00Z'),
  ]

  it('nennt kommende Termine zuerst und jede Serie nur einmal', () => {
    expect(matchEvents(ITEMS, 'versammlung', '2026-11-17').map((o) => o.event_id)).toEqual([
      3, 4, 1,
    ])
    expect(matchEvents(ITEMS, 'zugabend', '2026-11-17').map((o) => o.starts_at)).toEqual([
      '2026-11-20T19:00:00Z',
    ])
    expect(matchEvents(ITEMS, ' ', '2026-11-17')).toEqual([])
  })

  it('zeigt Termine als eigene Gruppe und öffnet den Termin im Kalender', async () => {
    fakeApi(
      new Proxy(
        {},
        {
          get: (_t, key) =>
            String(key).startsWith('GET /api/orgs/7/events/?from=')
              ? () => ({ status: 200, body: { items: ITEMS, categories: [] } })
              : undefined,
        },
      ),
    )
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <QuickSearch pages={[]} memberOrg={null} eventBase="/api/orgs/7/" />
        <Ort />
      </MemoryRouter>,
    )
    await user.click(screen.getByRole('button', { name: /Schnellsuche/ }))
    await user.type(screen.getByRole('combobox', { name: 'Seite oder Termin suchen' }), 'general')
    const hit = await screen.findByRole('option', { name: /Generalversammlung/ })
    expect(hit).toHaveTextContent('06.03.2026')
    await user.click(hit)
    expect(screen.getByTestId('ort')).toHaveTextContent('/termine?termin=1&datum=2026-03-06')
  })
})
