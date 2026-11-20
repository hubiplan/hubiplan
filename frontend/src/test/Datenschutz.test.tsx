import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const activity = {
  id: null,
  key: 'members',
  module: 'members',
  title: 'Mitgliederverwaltung',
  purpose: 'Durchführung der Mitgliedschaft',
  legal_basis: 'Art. 6 Abs. 1 lit. b DSGVO',
  subjects: 'Mitglieder',
  categories: 'Name, Anschrift',
  recipients: 'Vorstand',
  third_country: 'keine',
  retention: '24 Monate nach Austritt',
  hidden: false,
}
const breach = {
  id: 5,
  title: 'Liste an falschen Verteiler',
  discovered_at: '2099-01-10T08:00:00Z',
  occurred: '',
  description: 'Mitgliederliste ging an einen falschen Verteiler.',
  categories: '',
  affected: '',
  consequences: '',
  measures: '',
  risk: 'risk',
  report_deadline: '2099-01-13T08:00:00Z',
  reported_at: null,
  report_reference: '',
  no_report_reason: '',
  notified_at: null,
  closed_at: null,
  status: 'report_due',
  created_by: 'Erika Muster',
  version: 1,
}

function show(permissions: string[], path = '/dsgvo') {
  const edit = permissions.includes('privacy.edit')
  const overview = {
    controller: {
      name: 'Musterverein e. V.',
      address: 'Musterweg 1, 12345 Musterstadt',
      representatives: 'Erika Muster',
      contact: 'info@example.org',
    },
    settings: {
      dpo_name: '',
      dpo_contact: '',
      hoster: 'Muster-Hosting',
      toms: 'HTTPS',
      version: 1,
    },
    activities: [
      activity,
      { ...activity, key: 'circulars', title: 'Rundschreiben und Glückwünsche', hidden: true },
    ],
    processors: [
      { id: 3, name: 'Muster Mailversand', agreement: null },
      {
        id: 4,
        name: 'Muster Druck',
        agreement: { id: 1, title: 'AV-Vertrag', start: '2099-01-01', end: null },
      },
    ],
    open_breaches: [breach],
    can_edit: edit,
    can_partners: true,
  }
  const api = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ permissions })],
    }),
    'GET /api/orgs/7/privacy/': () => ({ status: 200, body: overview }),
    'PUT /api/orgs/7/privacy/settings/': (init?: RequestInit) => ({
      status: 200,
      body: { ...JSON.parse(String(init?.body ?? '{}')), version: 2 },
    }),
    'POST /api/orgs/7/privacy/hide/': () => ({ status: 200, body: { hidden_keys: [] } }),
    'GET /api/orgs/7/privacy/breaches/': () => ({
      status: 200,
      body: { items: [breach], can_edit: edit },
    }),
    'POST /api/orgs/7/privacy/breaches/': (init?: RequestInit) => ({
      status: 201,
      body: { ...breach, id: 6, ...JSON.parse(String(init?.body ?? '{}')) },
    }),
    'PATCH /api/orgs/7/privacy/breaches/5/': () => ({
      status: 200,
      body: { ...breach, status: 'closed', closed_at: '2099-01-11T08:00:00Z', version: 2 },
    }),
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

describe('Datenschutz-Werkzeuge', () => {
  it('zeigt das Verzeichnis und speichert die Angaben', async () => {
    const api = show(['privacy.view', 'privacy.edit'])
    expect(await screen.findByText('Mitgliederverwaltung')).toBeInTheDocument()
    expect(screen.getByText('Musterverein e. V.')).toBeInTheDocument()
    expect(screen.getByText(/wartet auf die Meldung/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Verzeichnis als PDF' })).toHaveAttribute(
      'href',
      '/api/orgs/7/privacy/?als=pdf',
    )
    fireEvent.change(screen.getByLabelText('Datenschutzbeauftragte/r'), {
      target: { value: 'Dora Datenschutz' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'PUT /api/orgs/7/privacy/settings/')).toBe(true),
    )
    const body = JSON.parse(
      String(api.find((c) => c.key === 'PUT /api/orgs/7/privacy/settings/')!.init?.body),
    )
    expect(body.dpo_name).toBe('Dora Datenschutz')
    // Ausgeblendeten Vorschlag wieder aufnehmen
    const hidden = screen.getByRole('heading', { name: 'Ausgeblendet' }).nextElementSibling!
    fireEvent.click(within(hidden as HTMLElement).getByRole('button', { name: 'Wieder aufnehmen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/privacy/hide/')).toBe(true),
    )
  })

  it('zeigt Auftragsverarbeiter mit fehlendem Vertrag', async () => {
    show(['privacy.view'], '/dsgvo/auftragsverarbeiter')
    const name = await screen.findByText('Muster Mailversand')
    expect(within(name.closest('li')!).getByText('Vertrag fehlt')).toBeInTheDocument()
    expect(screen.getByText('Muster-Hosting')).toBeInTheDocument()
    expect(screen.getByText(/Bei 1 Auftragsverarbeitern fehlt/)).toBeInTheDocument()
  })

  it('erfasst und schließt Datenpannen', async () => {
    const api = show(['privacy.view', 'privacy.edit'], '/dsgvo/datenpannen')
    const title = await screen.findByText('Liste an falschen Verteiler')
    const row = title.closest('li')!
    expect(within(row).getByText('Meldung offen')).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Abschließen' }))
    expect(await within(row).findByText('abgeschlossen')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Datenpanne erfassen' }))
    fireEvent.change(screen.getByLabelText(/Kurzbezeichnung/), {
      target: { value: 'USB-Stick verloren' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Datenpanne speichern' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/privacy/breaches/')).toBe(true),
    )
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/orgs/7/privacy/breaches/')!.init?.body),
    )
    expect(body.title).toBe('USB-Stick verloren')
    expect(body.discovered_at).toMatch(/Z$/)
  })

  it('zeigt Lesenden keine Bearbeitung', async () => {
    show(['privacy.view'], '/dsgvo/datenpannen')
    await screen.findByText('Liste an falschen Verteiler')
    expect(screen.queryByRole('button', { name: 'Datenpanne erfassen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument()
  })
})
