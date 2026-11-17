// UX-Audit 16.11.2026: Sitzung abgelaufen (VW-36), Wiederherstellungscodes (VW-48),
// Rückgängig-Hinweis außerhalb des Menüs (VW-01).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { resetUndo } from '../components/undo.ts'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const ORG = testOrg({ permissions: ['members.view', 'members.edit'] })
const base = '/api/orgs/7'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => resetUndo())

describe('Abgelaufene Sitzung', () => {
  it('führt nach einer 403-Antwort zur Anmeldung und sagt warum', async () => {
    let expired = false
    fakeApi({
      [SESSION]: () => (expired ? { status: 401, body: { status: 401 } } : loggedIn()),
      'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
      [`GET ${base}/members/11/`]: () => {
        expired = true
        return { status: 403, body: { detail: 'Anmeldedaten fehlen.' } }
      },
    })
    renderAt('/mitglieder/11')
    expect(await screen.findByRole('heading', { name: 'Anmelden' })).toBeInTheDocument()
    expect(screen.getByText(/Deine Sitzung ist abgelaufen/)).toBeInTheDocument()
  })

  it('bleibt bei fehlender Berechtigung angemeldet', async () => {
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
      [`GET ${base}/members/11/`]: () => ({ status: 403, body: { detail: 'Keine Berechtigung.' } }),
    })
    renderAt('/mitglieder/11')
    // Die Sitzung wird nach der 403-Antwort einmal geprüft und besteht
    await waitFor(() => expect(calls.filter((c) => c.key === SESSION).length).toBeGreaterThan(1))
    expect(screen.queryByRole('heading', { name: 'Anmelden' })).not.toBeInTheDocument()
  })
})

describe('Wiederherstellungscodes', () => {
  const TOTP = '/_allauth/browser/v1/account/authenticators/totp'
  const CODES = '/_allauth/browser/v1/account/authenticators/recovery-codes'

  it('lassen sich später anzeigen und neu erzeugen', async () => {
    let codes = ['11112222', '33334444']
    fakeApi({
      [SESSION]: loggedIn,
      [`GET ${TOTP}`]: () => ({ status: 200, body: { status: 200, data: { type: 'totp' } } }),
      [`GET ${CODES}`]: () => ({
        status: 200,
        body: { status: 200, data: { unused_codes: codes } },
      }),
      [`POST ${CODES}`]: () => {
        codes = ['55556666']
        return { status: 200, body: { status: 200, data: { unused_codes: codes } } }
      },
    })
    renderAt('/mein-konto/anmeldung')
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Wiederherstellungscodes anzeigen' }),
    )
    expect(await screen.findByText('11112222')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Codes kopieren' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Als Textdatei speichern' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Neue Codes erzeugen' }))
    // Rückfrage nennt die Folge und die Handlung
    expect(
      await screen.findByText('Die bisherigen Codes gelten danach nicht mehr.'),
    ).toBeInTheDocument()
    const confirm = screen.getAllByRole('button', { name: 'Neue Codes erzeugen' })
    await user.click(confirm[confirm.length - 1])
    expect(await screen.findByText('55556666')).toBeInTheDocument()
    expect(screen.queryByText('11112222')).not.toBeInTheDocument()
  })

  it('fragen vor dem Anzeigen nach dem Passwort, wenn der Server es verlangt', async () => {
    let confirmed = false
    fakeApi({
      [SESSION]: loggedIn,
      [`GET ${TOTP}`]: () => ({ status: 200, body: { status: 200, data: { type: 'totp' } } }),
      [`GET ${CODES}`]: () =>
        confirmed
          ? { status: 200, body: { status: 200, data: { unused_codes: ['77778888'] } } }
          : { status: 401, body: { status: 401 } },
      'POST /_allauth/browser/v1/auth/reauthenticate': () => {
        confirmed = true
        return loggedIn()
      },
    })
    renderAt('/mein-konto/anmeldung')
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Wiederherstellungscodes anzeigen' }),
    )
    await user.type(await screen.findByLabelText('Passwort'), 'geheim')
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }))
    expect(await screen.findByText('77778888')).toBeInTheDocument()
  })
})

describe('Rückgängig-Hinweis', () => {
  it('hängt am Dokument, nicht am Menü', async () => {
    const detail = { id: 11, person_id: 42, last_name: 'Muster', first_name: 'Erika' }
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
      [`GET ${base}/members/11/`]: () => ({ status: 200, body: detail }),
      [`DELETE ${base}/members/11/`]: () => ({ status: 204 }),
    })
    const { mutationListeners } = await import('../api/client.ts')
    renderAt('/mitglieder')
    await screen.findByRole('button', { name: 'Letzte Änderung rückgängig machen' })
    const headers = new Headers({
      'X-Change-Set': 'aaa',
      'X-Change-Undoable': '1',
      'X-Change-Kind': 'delete',
      'X-Change-Label': encodeURIComponent('Mitglied gelöscht'),
    })
    for (const listener of mutationListeners) listener(`${base}/members/11/`, 204, headers)
    const notice = await waitFor(() => {
      const found = document.querySelector('.undo-notice')
      expect(found).not.toBeNull()
      return found as HTMLElement
    })
    expect(notice.parentElement).toBe(document.body)
  })
})
