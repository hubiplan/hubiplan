// Einstellungen › API-Zugänge: anlegen, Schlüssel einmal zeigen, Bereiche (erfundene Daten).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider, useOrg } from '../org/OrgContext.tsx'
import { ApiAccessPage } from '../pages/settings/ApiAccessPage.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { settingsItems } from '../pages/settings/items.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})

const scopes = [
  {
    scope: 'einheit.lesen',
    label: 'Einheit lesen',
    description: 'Name, Anschrift, Kontakt, Logo und die Untereinheiten als Baum',
    unit_ok: true,
    needs: '',
    personal: false,
    write: false,
  },
  {
    scope: 'termine.lesen',
    label: 'Öffentliche Termine lesen',
    description: 'Termine mit der Sichtbarkeit „nach außen öffentlich“',
    unit_ok: true,
    needs: '',
    personal: false,
    write: false,
  },
  {
    scope: 'termine.mitglieder',
    label: 'Auch Termine für Mitglieder lesen',
    description: 'Zusätzlich Termine mit der Sichtbarkeit „Mitglieder“',
    unit_ok: true,
    needs: 'termine.lesen',
    personal: false,
    write: false,
  },
  {
    scope: 'vorstand.lesen',
    label: 'Vorstand und Ämter lesen',
    description: 'Rollen mit „auf der Webseite zeigen“',
    unit_ok: false,
    needs: '',
    personal: false,
    write: false,
  },
  {
    scope: 'mitglieder.lesen',
    label: 'Mitglieder lesen',
    description: 'Name, Geburtsdatum und Mitgliedsnummer',
    unit_ok: true,
    needs: '',
    personal: true,
    write: false,
  },
]

const access = {
  id: 4,
  name: 'Verbandssoftware',
  purpose: 'Terminliste des Verbands',
  recipient: 'Musterverband',
  scopes: ['einheit.lesen', 'termine.lesen'],
  unit: null,
  key_hint: 'Ab3x',
  key_created_at: '2026-11-22T08:00:00Z',
  previous_until: null,
  expires_at: '2027-11-20T22:59:59Z',
  allowed_networks: [],
  embeddable: false,
  state: 'idle',
  idle_at: '2027-02-20T08:00:00Z',
  created_at: '2026-11-22T08:00:00Z',
  created_by: 'Erika Beispiel',
  last_used_at: null,
  last_used_ip: '',
  request_count: 0,
  writes: false,
  write_count: 0,
  last_write_at: null,
  partner: null,
  legal_basis: '',
  legal_confirmed_at: null,
  legal_confirmed_by: '',
  third_country: false,
  member_fields: [],
  only_active: true,
  adults_only: false,
  report_level: 'a',
  personal: false,
  webhook_url: '',
  webhook_events: [],
  webhook_state: 'off',
  webhook_last_ok_at: null,
  webhook_last_error: '',
  records_read: 0,
  reads: [],
}

const personalAccess = {
  ...access,
  id: 5,
  name: 'Mitgliederabgleich',
  state: 'active',
  scopes: ['mitglieder.lesen'],
  partner: { id: 31, name: 'Musterbund Software GmbH' },
  legal_basis: 'processing',
  legal_confirmed_at: '2026-11-22T09:00:00Z',
  legal_confirmed_by: 'Erika Beispiel',
  member_fields: ['contact'],
  personal: true,
  webhook_url: 'https://verband.example/hubiplan',
  webhook_events: ['member.changed'],
  webhook_state: 'paused',
  records_read: 12,
  reads: [{ at: '2026-11-22T10:00:00Z', scope: 'mitglieder.lesen', count: 12 }],
}

const list = (accesses: object[]) => ({
  address: 'https://verein.example/api/partner/v1/',
  docs: 'https://verein.example/api/partner/v1/openapi.json',
  requests_per_hour: 600,
  writes_per_hour: 60,
  max_days: 365,
  idle_days: 90,
  overlap_days: 7,
  scopes,
  units: [{ id: 12, name: 'Jugend' }],
  partners: [{ id: 31, name: 'Musterbund Software GmbH', processor: false }],
  member_fields: ['contact', 'membership', 'units'],
  webhook_events: [
    { event: 'member.changed', label: 'Mitglied geändert', scope: 'mitglieder.lesen' },
    { event: 'event.created', label: 'Termin angelegt', scope: 'termine.lesen' },
  ],
  log_days: 90,
  accesses,
})

function WhenActive() {
  const { active } = useOrg()
  return active ? <ApiAccessPage /> : null
}

function renderPage(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': session,
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ type: 'club', permissions: ['settings.view', 'api.manage'] })],
    }),
    ...routes,
  })
  render(
    <MemoryRouter>
      <AuthProvider>
        <OrgProvider>
          <WhenActive />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('API-Zugänge', () => {
  it('Menüpunkt nur mit Modul und Zusatzrecht', () => {
    const has = (org: object) =>
      settingsItems(org as unknown as OrgSummary).some((item) => item.to === '/einstellungen/api')
    const permissions = ['settings.view', 'api.manage']
    expect(has(testOrg({ type: 'club', permissions, modules: ['api'] }))).toBe(true)
    expect(has(testOrg({ type: 'club', permissions, modules: [] }))).toBe(false)
    expect(has(testOrg({ type: 'club', permissions: ['settings.view'], modules: ['api'] }))).toBe(
      false,
    )
  })

  it('anlegen zeigt den Schlüssel einmal; ein Bereich nimmt den vorausgesetzten mit', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([]) }),
      'POST /api/orgs/7/api-accesses/': () => ({
        status: 201,
        body: { ...access, state: 'active', key: 'hpk_erfundenerSchluessel' },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText('Noch keine API-Zugänge angelegt.')).toBeInTheDocument()
    expect(screen.getByText('https://verein.example/api/partner/v1/')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    await user.type(screen.getByLabelText(/^Name/), 'Verbandssoftware')
    await user.click(screen.getByRole('checkbox', { name: 'Auch Termine für Mitglieder lesen' }))
    expect(screen.getByRole('checkbox', { name: 'Öffentliche Termine lesen' })).toBeChecked()
    // Für eine Untereinheit gibt es den Vorstand nicht
    await user.selectOptions(screen.getByLabelText('Gilt für'), '12')
    expect(screen.getByRole('checkbox', { name: /Vorstand und Ämter lesen/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    expect(await screen.findByDisplayValue('hpk_erfundenerSchluessel')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/orgs/7/api-accesses/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      name: 'Verbandssoftware',
      unit: 12,
      scopes: ['termine.mitglieder', 'termine.lesen'],
      allowed_networks: [],
      embeddable: false,
    })
    await user.click(screen.getByRole('button', { name: 'Fertig' }))
    expect(screen.queryByDisplayValue('hpk_erfundenerSchluessel')).not.toBeInTheDocument()
    expect(screen.getByText(/Schlüssel endet auf …Ab3x/)).toBeInTheDocument()
  })

  it('ruhender Zugang lässt sich wieder einschalten', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([access]) }),
      'POST /api/orgs/7/api-accesses/4/resume/': () => ({
        status: 200,
        body: { ...access, state: 'active' },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText('ruht')).toBeInTheDocument()
    expect(screen.getByText('Einheit lesen, Öffentliche Termine lesen')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Wieder einschalten' }))
    expect(await screen.findByText('aktiv')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/orgs/7/api-accesses/4/resume/')).toBe(true)
  })

  it('Personendaten: Empfänger, Rechtsgrundlage und Bestätigung gehen mit', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([]) }),
      'POST /api/orgs/7/api-accesses/': () => ({
        status: 201,
        body: {
          ...personalAccess,
          webhook_state: 'ok',
          key: 'hpk_erfunden',
          webhook_secret: 'hpw_erfunden',
        },
      }),
    })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Zugang anlegen' }))
    await user.type(screen.getByLabelText(/^Name/), 'Mitgliederabgleich')
    // Ohne Bereich mit Personendaten gibt es die Felder dazu nicht
    expect(screen.queryByLabelText('Rechtsgrundlage')).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Mitglieder lesen' }))
    await user.click(screen.getByRole('checkbox', { name: 'Kontakt und Anschrift' }))
    await user.selectOptions(screen.getByLabelText('Empfänger (Geschäftspartner)'), '31')
    await user.selectOptions(screen.getByLabelText('Rechtsgrundlage'), 'processing')
    await user.click(screen.getByRole('checkbox', { name: /^Ich bestätige/ }))
    await user.type(
      screen.getByLabelText('Adresse für Benachrichtigungen'),
      'https://verband.example/hubiplan',
    )
    // Nur Ereignisse zu gewählten Bereichen stehen zur Wahl
    expect(screen.queryByRole('checkbox', { name: 'Termin angelegt' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Mitglied geändert' }))
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    expect(await screen.findByDisplayValue('hpw_erfunden')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/orgs/7/api-accesses/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      scopes: ['mitglieder.lesen'],
      partner: 31,
      legal_basis: 'processing',
      legal_confirmed: true,
      member_fields: ['contact'],
      only_active: true,
      adults_only: false,
      webhook_url: 'https://verband.example/hubiplan',
      webhook_events: ['member.changed'],
    })
    expect(screen.getByText(/Empfänger: Musterbund Software GmbH/)).toBeInTheDocument()
  })

  it('zeigt Abrufe von Personendaten und schaltet ruhende Benachrichtigungen wieder ein', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([personalAccess]) }),
      'PATCH /api/orgs/7/api-accesses/5/': () => ({
        status: 200,
        body: { ...personalAccess, webhook_state: 'ok' },
      }),
    })
    const user = userEvent.setup()
    expect(
      await screen.findByText(/12 Datensätze mit Personendaten in den letzten 90 Tagen abgerufen/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Benachrichtigungen ruhen/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Benachrichtigungen wieder einschalten' }))
    expect(
      await screen.findByText('Benachrichtigungen an https://verband.example/hubiplan'),
    ).toBeInTheDocument()
    const patch = calls.find((c) => c.key === 'PATCH /api/orgs/7/api-accesses/5/')
    expect(JSON.parse(String(patch?.init?.body))).toEqual({ webhook_resume: true })
  })

  it('Schreiben steht eigens zur Wahl und am Zugang', async () => {
    const write = {
      scope: 'termine.schreiben',
      label: 'Termine anlegen und ändern',
      description: 'Einzelne Termine anlegen, ändern und absagen',
      unit_ok: true,
      needs: '',
      personal: false,
      write: true,
    }
    const writing = {
      ...access,
      scopes: ['termine.schreiben'],
      writes: true,
      write_count: 7,
      last_write_at: '2026-11-22T09:30:00Z',
    }
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({
        status: 200,
        body: { ...list([writing]), scopes: [...scopes, write] },
      }),
      'POST /api/orgs/7/api-accesses/': () => ({
        status: 201,
        body: { ...writing, id: 6, name: 'Zeitmessung', key: 'hpk_erfunden' },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText(/Darf schreiben: 7 schreibende Anfragen/)).toBeInTheDocument()
    expect(screen.getByText(/davon höchstens 60 schreibende/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    // Ohne Zutun ist kein schreibender Bereich gewählt
    const box = screen.getByRole('checkbox', { name: 'Termine anlegen und ändern' })
    expect(box).not.toBeChecked()
    expect(screen.getByRole('group', { name: 'Was der Zugang schreiben darf' })).toContainElement(
      box,
    )
    await user.type(screen.getByLabelText(/^Name/), 'Zeitmessung')
    await user.click(box)
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    await screen.findByDisplayValue('hpk_erfunden')
    const post = calls.find((c) => c.key === 'POST /api/orgs/7/api-accesses/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ scopes: ['termine.schreiben'] })
  })
})
