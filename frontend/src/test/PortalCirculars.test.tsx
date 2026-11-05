import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { RequireAuth } from '../auth/RequireAuth.tsx'
import { LoginPage } from '../pages/LoginPage.tsx'
import { PortalCirculars } from '../pages/portal/PortalCirculars.tsx'
import { portalCircularApi } from '../api/circulars.ts'
import type { ReceivedCircular } from '../api/circulars.ts'
import { setCatalogForTest } from '../i18n/index.ts'
import en from '../i18n/en.json'
import { fakeApi, testUser } from './fakeApi.ts'

const row: ReceivedCircular = {
  id: 17,
  subject: 'Einladung',
  kind_label: 'Vereinsmitteilung',
  sender: 'Musterverein',
  sent_at: '2026-11-05',
  channel: 'app',
  body: '**Wichtig**\n\n- Papier\n- Stift',
  attachments: [{ id: 8, name: 'Einladung.pdf', size: 23, url: '/api/files/8/' }],
}
function routes() {
  return {
    'GET /api/portal/9/circulars/': () => ({ status: 200, body: [row] }),
    'GET /api/portal/9/circulars/17/': () => ({ status: 200, body: row }),
    'GET /api/portal/9/circulars/settings/': () => ({ status: 200, body: { info_opt_out: false } }),
  }
}
function Location() {
  const at = useLocation(),
    go = useNavigate()
  return (
    <>
      <span data-testid="location">{at.pathname + at.search}</span>
      <button onClick={() => go(-1)}>Browser zurück</button>
      <button onClick={() => go('?zugang=9&schreiben=18')}>Anderes Schreiben</button>
    </>
  )
}
function view(at = '/mein-bereich/rundschreiben?zugang=9&schreiben=17') {
  return render(
    <MemoryRouter initialEntries={[at]}>
      <PortalCirculars accessId={9} />
      <Location />
    </MemoryRouter>,
  )
}
afterEach(() => setCatalogForTest('de'))
describe('Genaues Rundschreiben aus der App', () => {
  it('erhält Zugang und Schreiben bei normaler Browseranmeldung', async () => {
    fakeApi({
      ...routes(),
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 401,
        body: { status: 401, data: { flows: [] }, meta: {} },
      }),
      'POST /_allauth/browser/v1/auth/login': () => ({
        status: 200,
        body: {
          status: 200,
          data: { user: testUser, methods: [] },
          meta: { is_authenticated: true },
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/mein-bereich/rundschreiben?zugang=9&schreiben=17']}>
        <AuthProvider>
          <Routes>
            <Route path="/anmelden" element={<LoginPage />} />
            <Route
              path="/mein-bereich/rundschreiben"
              element={
                <RequireAuth>
                  <PortalCirculars accessId={9} />
                </RequireAuth>
              }
            />
          </Routes>
          <Location />
        </AuthProvider>
      </MemoryRouter>,
    )
    await userEvent.type(await screen.findByLabelText('E-Mail-Adresse'), 'mitglied@example.org')
    await userEvent.type(screen.getByLabelText('Passwort'), 'Nur-im-Test-123')
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }))
    expect(await screen.findByRole('heading', { name: 'Einladung' })).toHaveFocus()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/mein-bereich/rundschreiben?zugang=9&schreiben=17',
    )
    expect(screen.getByRole('link', { name: 'Einladung.pdf' })).toHaveAttribute(
      'href',
      '/api/files/8/',
    )
    expect(screen.getByText('Wichtig').tagName).toBe('STRONG')
    expect(screen.getAllByRole('listitem')).toHaveLength(4) // zwei Textpunkte, Anhang, Übersicht
  })
  it('lädt ein direkt verlinktes Schreiben auch außerhalb der Liste und bietet Fehlerbehebung', async () => {
    let fail = true
    fakeApi({
      ...routes(),
      'GET /api/portal/9/circulars/': () => ({ status: 200, body: [] }),
      'GET /api/portal/9/circulars/17/': () =>
        fail ? { status: 404, body: { detail: 'Nicht gefunden.' } } : { status: 200, body: row },
    })
    view()
    expect(await screen.findByRole('alert')).toHaveTextContent('Nicht gefunden.')
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Erneut laden' }))
    expect(await screen.findByRole('heading', { name: 'Einladung' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Zur Übersicht' }))
    expect(screen.queryByRole('link', { name: 'Einladung.pdf' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mitteilungen' })).toHaveFocus()
  })
  it('stellt bei Browser-Zurück den Fokus an der auslösenden Zeile wieder her', async () => {
    fakeApi(routes())
    view('/mein-bereich/rundschreiben?zugang=9')
    const opener = await screen.findByRole('button', { name: 'Einladung' })
    await userEvent.click(opener)
    expect(await screen.findByRole('heading', { name: 'Einladung' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Browser zurück' }))
    await waitFor(() => expect(opener).toHaveFocus())
    expect(screen.getByTestId('location')).not.toHaveTextContent('schreiben=')
  })
  it('zeigt nach einem Wechsel keine verspäteten alten Inhalte', async () => {
    fakeApi(routes())
    let finish!: (value: typeof row) => void
    vi.spyOn(portalCircularApi, 'get').mockImplementation((_access, id) =>
      id === 17
        ? new Promise((resolve) => {
            finish = resolve
          })
        : Promise.resolve({ ...row, id: 18, subject: 'Zweites Schreiben' }),
    )
    view()
    await waitFor(() => expect(finish).toBeTypeOf('function'))
    await userEvent.click(screen.getByRole('button', { name: 'Anderes Schreiben' }))
    expect(await screen.findByRole('heading', { name: 'Zweites Schreiben' })).toBeInTheDocument()
    await act(async () => finish(row))
    expect(screen.queryByRole('heading', { name: 'Einladung' })).not.toBeInTheDocument()
  })
  it.each(['0', '-1', '1e3', '9007199254740992', 'abc'])(
    'weist ungültiges Ziel %s ohne Detailabruf zurück',
    async (id) => {
      const calls = fakeApi(routes())
      view(`/?schreiben=${id}`)
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Dieser Link zur Mitteilung ist ungültig.',
      )
      await screen.findByRole('button', { name: 'Einladung' })
      expect(calls.filter((c) => /circulars\/\d+\/$/.test(c.key))).toHaveLength(0)
    },
  )
  it('erhält beim Speichern den Fokus und verhindert weitere Änderungen bis zur Bestätigung', async () => {
    fakeApi(routes())
    let finish!: (value: { info_opt_out: boolean }) => void
    const save = vi.spyOn(portalCircularApi, 'setOptOut').mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    view('/')
    const checkbox = await screen.findByRole('checkbox')
    await userEvent.click(checkbox)
    expect(checkbox).toHaveFocus()
    expect(checkbox).not.toBeDisabled()
    expect(checkbox).toHaveAttribute('aria-busy', 'true')
    expect(checkbox).toHaveAttribute('aria-disabled', 'true')
    await userEvent.keyboard(' ')
    await userEvent.click(checkbox)
    expect(save).toHaveBeenCalledTimes(1)
    expect(checkbox).toBeChecked()
    await act(async () => finish({ info_opt_out: true }))
    expect(screen.getByRole('status')).toHaveTextContent(
      'Informationen per E-Mail sind abbestellt.',
    )
    expect(checkbox).toHaveFocus()
    expect(checkbox).not.toBeChecked()
    expect(checkbox).not.toHaveAttribute('aria-busy')
  })
  it('bestätigt nur erfolgreiche Änderungen, räumt alte Erfolge weg und erhält die Serverauswahl', async () => {
    setCatalogForTest('en', en)
    let fail = false
    fakeApi({
      ...routes(),
      'PUT /api/portal/9/circulars/settings/': () =>
        fail
          ? { status: 503, body: { detail: 'Offline' } }
          : { status: 200, body: { info_opt_out: true } },
    })
    view('/')
    const checkbox = await screen.findByRole('checkbox')
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('')
    await userEvent.click(checkbox)
    await waitFor(() =>
      expect(status).toHaveTextContent('Information emails have been unsubscribed.'),
    )
    expect(status).toHaveAttribute('aria-atomic', 'true')
    expect(checkbox).not.toBeChecked()
    fail = true
    await userEvent.click(checkbox)
    expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
    expect(status).toHaveTextContent('')
    expect(checkbox).not.toBeChecked()
  })
})
