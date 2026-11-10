import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { PlatformOrgsPage } from '../pages/platform/PlatformPages.tsx'
import { fakeApi, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})

const bund = {
  id: 7,
  type: 'federation',
  type_label: 'Dachverband',
  keeps_members: false,
  can_switch_members: false,
  federation: null,
  federation_name: null,
  name: 'Testbund',
  postal_code: '12345',
  city: 'Musterstadt',
  federation_member_access: 'none',
  enabled_modules: [],
  is_active: true,
}

function eraseState(extra: Record<string, unknown> = {}) {
  return {
    requested_at: null,
    requested_by: '',
    wait_days: 30,
    wait_until: null,
    retention_until: null,
    holds: [],
    has_finance: false,
    possible_from: null,
    blockers: [],
    can_erase: false,
    needs_code: false,
    ...extra,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <OrgProvider>
          <PlatformOrgsPage />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Einheit anlegen auf der Plattform', () => {
  it('legt zuerst still und merkt die Löschung vor', async () => {
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': session,
      'GET /api/platform/orgs/': () => ({ status: 200, body: [bund] }),
      'GET /api/platform/orgs/7/erase-state/': () => ({ status: 200, body: eraseState() }),
      'POST /api/platform/orgs/7/erase-request/': () => ({ status: 204 }),
    })
    renderPage()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    await user.click(
      await screen.findByRole('button', { name: 'Stilllegen und Löschung vormerken' }),
    )
    expect(screen.getByRole('button', { name: 'Stilllegen und vormerken' })).toBeDisabled()
    expect(screen.queryByLabelText('Eigenes Passwort')).toBeNull()
    await user.type(screen.getByLabelText('Name zur Löschbestätigung'), bund.name)
    await user.click(screen.getByRole('button', { name: 'Stilllegen und vormerken' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/platform/orgs/7/erase-request/')).toBe(true),
    )
    const post = calls.find((call) => call.key === 'POST /api/platform/orgs/7/erase-request/')
    expect(JSON.parse(String(post?.init?.body))).toEqual({ confirmation: bund.name })
  })

  it('zeigt Fristen und löscht erst mit Passwort, Code und Bestätigung der Fristen', async () => {
    let deleted = false
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': session,
      'GET /api/platform/orgs/': () => ({
        status: 200,
        body: deleted
          ? []
          : [{ ...bund, is_active: false, erase_requested_at: '2026-01-02T10:00:00Z' }],
      }),
      'GET /api/platform/orgs/7/erase-state/': () => ({
        status: 200,
        body: eraseState({
          requested_at: '2026-01-02T10:00:00Z',
          retention_until: '2037-01-01',
          possible_from: '2037-01-01',
          has_finance: true,
          can_erase: true,
          needs_code: true,
        }),
      }),
      'POST /api/platform/orgs/7/erase/': () => {
        deleted = true
        return { status: 204 }
      },
    })
    renderPage()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Bearbeiten' }))
    expect(await screen.findByText(/Aufbewahrungsfristen laufen bis/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /ist aktiv/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Endgültig löschen' }))
    const submit = screen.getByRole('button', { name: 'Unwiderruflich löschen' })
    await user.type(screen.getByLabelText('Name zur Löschbestätigung'), bund.name)
    await user.type(screen.getByLabelText('Eigenes Passwort'), 'geheim')
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Fristen bestätigt von/), 'Kassenprüfer Muster')
    await user.type(screen.getByLabelText('Code aus der Authentifizierungs-App'), '123456')
    await user.click(submit)
    await waitFor(() => expect(screen.queryByText(bund.name)).toBeNull())
    const post = calls.find((call) => call.key === 'POST /api/platform/orgs/7/erase/')
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      confirmation: bund.name,
      confirmed_by: 'Kassenprüfer Muster',
      password: 'geheim',
      code: '123456',
    })
  })

  it('ein Knopf, Schalter statt Art, Bezeichnung folgt dem Schalter', async () => {
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': session,
      'GET /api/platform/orgs/': () => ({ status: 200, body: [bund] }),
      'POST /api/platform/orgs/': () => ({ status: 201, body: { ...bund, id: 8 } }),
    })
    renderPage()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Einheit anlegen' }))
    expect(screen.queryByText(/Übergeordnete Einheit anlegen/)).toBeNull()

    const keeps = screen.getByRole('checkbox', { name: /Führt eigene Mitglieder/ })
    expect(keeps).toBeChecked()
    expect(screen.getByRole('heading', { name: 'Verein anlegen' })).toBeInTheDocument()

    await user.click(keeps)
    expect(screen.getByRole('heading', { name: 'Dachverband anlegen' })).toBeInTheDocument()
    expect(screen.getByText(/Zugriff auf Mitgliedsdaten/)).toBeInTheDocument()

    // Unter einer übergeordneten Einheit immer mit eigenen Mitgliedern
    await user.selectOptions(screen.getByLabelText('Übergeordnete Einheit'), '7')
    expect(keeps).toBeChecked()
    expect(keeps).toBeDisabled()

    await user.type(screen.getByLabelText(/Vollständiger Name/), 'Neuer Verein')
    await user.type(screen.getByLabelText(/Gründungsjahr/), '2001')
    await user.type(screen.getByLabelText(/Straße und Hausnummer/), 'Weg 2')
    await user.type(screen.getByLabelText(/^PLZ/), '54321')
    await user.type(screen.getByLabelText(/^Ort/), 'Neustadt')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/platform/orgs/')).toBe(true))
    const post = calls.find((c) => c.key === 'POST /api/platform/orgs/')
    const body = JSON.parse(String(post?.init?.body))
    expect(body.federation).toBe(7)
    expect(body.type).toBeUndefined()
    expect(body.label).toBe('Verein')
  })
})
