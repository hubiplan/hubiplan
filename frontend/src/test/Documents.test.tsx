import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const base = '/api/orgs/7/documents/'

function renderApp(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

const version = (id: number, name: string) => ({
  id,
  name,
  size: 4096,
  content_type: 'application/pdf',
  uploaded_at: '2026-02-15T10:00:00Z',
  uploaded_by: 'Hanna Hubertus',
  url: `${base}versions/${id}/`,
  inline: true,
})

const doc = (id: number, title: string, note = '') => ({
  id,
  folder: 1,
  title,
  date: '2026-02-14',
  note,
  created_at: '2026-02-15T10:00:00Z',
  created_by: 'Hanna Hubertus',
  current: version(id * 10, `${title}.pdf`),
  version_count: 2,
  versions: [version(id * 10, `${title}.pdf`), version(id * 10 + 1, 'alt.pdf')],
})

const overview = (canManage = true) => ({
  folders: [
    {
      id: 1,
      name: 'Protokolle',
      visibility: 'board',
      visibility_label: 'nur Vorstand',
      shared_up: false,
      documents: [doc(1, 'Jahreshauptversammlung', 'mit Neuwahlen'), doc(2, 'Vorstandssitzung')],
      public_url: null,
    },
  ],
  can_manage: canManage,
  visibilities: [
    { value: 'board', label: 'nur Vorstand' },
    { value: 'members', label: 'alle Mitglieder' },
    { value: 'public', label: 'öffentlich per Link' },
  ],
  used_bytes: 3 * 1024 * 1024,
  trash_count: 1,
  share_up_label: 'Für den Dachverband freigeben (nur lesen)',
  org_kind: 'club',
  from_below: [
    {
      id: 12,
      name: 'Zugprotokolle',
      visibility: 'board',
      visibility_label: 'nur Vorstand',
      shared_up: true,
      documents: [{ ...doc(4, 'Zugversammlung'), folder: 12 }],
      from: 'Jägerzug',
    },
  ],
  shared: [
    {
      id: 9,
      name: 'Rundschreiben',
      visibility: 'clubs',
      visibility_label: 'Vereine des Dachverbands',
      shared_up: false,
      documents: [{ ...doc(3, 'Meldebogen'), folder: 9 }],
      from: 'Testbund',
    },
  ],
})

function setup(perms: string[], extra = {}) {
  return fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg({ permissions: perms })] }),
    [`GET ${base}`]: () => ({ status: 200, body: overview(perms.includes('docs.manage')) }),
    'GET /api/orgs/7/statutes/': () => ({
      status: 200,
      body: {
        versions: [],
        publication: { is_public: false, pdf_url: null, info_url: null },
        can_manage: false,
      },
    }),
    ...extra,
  })
}

describe('Dokumente', () => {
  it('zeigt Ordner, Freigaben des Dachverbands, Platz und sucht in Titel und Bemerkung', async () => {
    setup(['docs.view', 'docs.manage'])
    renderApp('/dokumente')
    const nav = within(await screen.findByRole('navigation', { name: 'Module' }))
    expect(await nav.findByRole('link', { name: 'Dokumente' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Protokolle/ })).toBeInTheDocument()
    expect(screen.getByText(/Belegter Platz: 3,0 MB · 1 im Papierkorb/)).toBeInTheDocument()
    // „Satzung“ steht als Ordner und, sobald geladen, auch als Satzungsbereich auf der Seite
    expect(screen.getAllByText('Satzung').length).toBeGreaterThan(0)
    expect(screen.getByText('Vom Dachverband')).toBeInTheDocument()
    expect(screen.getByText('von Testbund')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Papierkorb' })).toBeInTheDocument()
    expect(screen.getByText('Von den Abteilungen')).toBeInTheDocument()
    expect(screen.getByText('von Jägerzug')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Suchen (Ordner, Titel und Bemerkung)'), 'neuwahl')
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    expect(screen.queryByText('Vorstandssitzung')).not.toBeInTheDocument()
    expect(screen.queryByText('Meldebogen')).not.toBeInTheDocument()
  })

  it('legt einen Ordner an und lädt hoch', async () => {
    const calls = setup(['docs.view', 'docs.manage'], {
      [`POST ${base}folders/`]: () => ({ status: 201, body: {} }),
      [`POST ${base}folders/1/documents/`]: () => ({ status: 201, body: {} }),
    })
    renderApp('/dokumente')
    await screen.findByRole('button', { name: /Protokolle/ })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Neuer Ordner' }))
    await user.type(screen.getByLabelText('Name'), 'Formulare')
    await user.selectOptions(screen.getAllByLabelText('Sichtbar für').at(-1)!, 'members')
    const shareBoxes = screen.getAllByLabelText('Für den Dachverband freigeben (nur lesen)')
    await user.click(shareBoxes.at(-1)!)
    await user.click(screen.getByRole('button', { name: 'Ordner anlegen' }))
    expect(await screen.findByText('Der Ordner wurde angelegt.')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${base}folders/`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      name: 'Formulare',
      visibility: 'members',
      shared_up: true,
    })

    const file = new File(['%PDF-1.4'], 'Einladung.pdf', { type: 'application/pdf' })
    await user.click(screen.getByText('Protokolle'))
    await user.upload(screen.getByLabelText('Datei für Protokolle'), file)
    await user.click(screen.getByRole('button', { name: 'Hochladen' }))
    expect(await screen.findByText('Das Dokument wurde hochgeladen.')).toBeInTheDocument()
    const upload = calls.find((c) => c.key === `POST ${base}folders/1/documents/`)
    const form = upload?.init?.body as FormData
    expect(form.get('title')).toBe('Einladung')
  })

  it('nur lesen: keine Verwaltung, kein Papierkorb', async () => {
    setup(['docs.view'])
    renderApp('/dokumente')
    await userEvent.setup().click(await screen.findByRole('button', { name: /Protokolle/ }))
    await screen.findByText('Jahreshauptversammlung')
    expect(screen.queryByRole('button', { name: 'Ordner anlegen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Papierkorb' })).not.toBeInTheDocument()
    expect(screen.queryByText('Neue Fassung')).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ansehen' }).length).toBeGreaterThan(0)
  })

  it('ohne Recht erscheint der Bereich nicht', async () => {
    setup(['members.view'])
    renderApp('/')
    const nav = within(await screen.findByRole('navigation', { name: 'Module' }))
    expect(await nav.findByRole('link', { name: 'Startseite' })).toBeInTheDocument()
    expect(nav.queryByRole('link', { name: 'Dokumente' })).not.toBeInTheDocument()
  })
})

describe('Dokumenten-Explorer', () => {
  it('startet mit Kacheln, navigiert per Tastatur und Ordnerpfad und behält den Ordner beim Ansichtswechsel', async () => {
    setup(['docs.view', 'docs.manage'])
    renderApp('/dokumente')
    const user = userEvent.setup()
    const folder = await screen.findByRole('button', { name: /Protokolle/ })
    expect(screen.getByRole('button', { name: 'Kachelansicht' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.queryByText('Jahreshauptversammlung')).not.toBeInTheDocument()
    folder.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Ordnerpfad' })).getByRole('button', {
        name: 'Protokolle',
      }),
    ).toHaveAttribute('aria-current', 'page')
    const file = new File(['%PDF'], 'neu.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Datei für Protokolle'), file)
    await user.click(screen.getByRole('button', { name: 'Listenansicht' }))
    expect(screen.getByRole('button', { name: 'Listenansicht' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect((screen.getByLabelText('Datei für Protokolle') as HTMLInputElement).files?.[0]).toBe(
      file,
    )
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    await user.click(
      within(screen.getByRole('navigation', { name: 'Ordnerpfad' })).getByRole('button', {
        name: 'Dokumente',
      }),
    )
    expect(screen.getByRole('button', { name: /Protokolle/ })).toBeInTheDocument()
    expect(screen.queryByText('Jahreshauptversammlung')).not.toBeInTheDocument()
  })

  it('sucht global nach Ordnernamen, Titel und Bemerkung und trimmt Leerzeichen', async () => {
    setup(['docs.view', 'docs.manage'])
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Protokolle/ }))
    const search = screen.getByRole('searchbox')
    await user.type(search, '  MELDEBOGEN  ')
    expect(screen.getByText('Meldebogen')).toBeInTheDocument()
    expect(screen.queryByText('Jahreshauptversammlung')).not.toBeInTheDocument()
    expect(screen.getByText('1 Treffer in eigenen und freigegebenen Ordnern.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    await user.clear(search)
    await user.type(search, '  neuwahlen  ')
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    await user.clear(search)
    await user.type(search, 'Rundschreiben')
    await user.click(screen.getByRole('button', { name: /Rundschreiben.*von Testbund/ }))
    expect(screen.getByRole('searchbox')).toHaveValue('')
    expect(screen.getByText('Meldebogen')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hochladen' })).not.toBeInTheDocument()
    await user.type(search, 'nirgendwo')
    expect(screen.getByText('Keine Ordner oder Dokumente passen zur Suche.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Suche zurücksetzen' }))
    expect(screen.getByText('Meldebogen')).toBeInTheDocument()
  })

  it.each([
    ['Satzung', '', 'Noch keine Satzung hinterlegt.'],
    ['Beitragsordnung', '?kind=fee_rules', 'Keine Beitragsordnung hinterlegt (optional).'],
    ['Gründungsurkunde', '?kind=founding_deed', 'Keine Gründungsurkunde hinterlegt (optional).'],
  ])('öffnet den festen Ordner %s mit bestehender Versionslogik', async (name, query, empty) => {
    const calls = setup(['docs.view', 'docs.manage'], {
      [`GET /api/orgs/7/statutes/${query}`]: () => ({
        status: 200,
        body: {
          versions: [],
          publication: { is_public: false, pdf_url: null, info_url: null },
          can_manage: false,
        },
      }),
    })
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: `${name} fester Ordner` }))
    expect(await screen.findByText(empty)).toBeInTheDocument()
    expect(calls.some((call) => call.key === `GET /api/orgs/7/statutes/${query}`)).toBe(true)
    expect(screen.queryByRole('button', { name: 'Ordner löschen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hochladen' })).not.toBeInTheDocument()
  })

  it('findet leere Ordner und feste Ordner, ohne falsche Nulltreffer-Meldung', async () => {
    const data = overview()
    data.folders[0].documents = []
    setup(['docs.view', 'docs.manage'], { [`GET ${base}`]: () => ({ status: 200, body: data }) })
    renderApp('/dokumente')
    await screen.findByRole('button', { name: /Protokolle/ })
    const user = userEvent.setup()
    await user.type(screen.getByRole('searchbox'), 'Protokolle')
    expect(screen.getByRole('button', { name: /Protokolle 0 Dokumente/ })).toBeInTheDocument()
    expect(screen.getByText('2 Treffer in eigenen und freigegebenen Ordnern.')).toBeInTheDocument()
    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), 'gruendungsurkunde')
    expect(
      screen.getByRole('button', { name: 'Gründungsurkunde fester Ordner' }),
    ).toBeInTheDocument()
    expect(screen.getByText('1 Treffer in eigenen und freigegebenen Ordnern.')).toBeInTheDocument()
  })

  it.each(['Zugprotokolle', 'Rundschreiben'])(
    'lässt Freigabe %s trotz Verwaltungsrecht nur lesen',
    async (name) => {
      setup(['docs.view', 'docs.manage'])
      renderApp('/dokumente')
      await userEvent.setup().click(await screen.findByRole('button', { name: new RegExp(name) }))
      expect(screen.getByText('Nur lesen')).toBeInTheDocument()
      expect(screen.queryByLabelText('Sichtbar für')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Ordner löschen' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Hochladen' })).not.toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Ansehen' })).toBeInTheDocument()
    },
  )

  it('erhält Sichtbarkeit, Freigabe, neue Fassungen, Bearbeiten, Verschieben und Papierkorb', async () => {
    const data = overview()
    data.folders.push({ ...data.folders[0], id: 2, name: 'Archiv', documents: [] })
    const calls = setup(['docs.view', 'docs.manage'], {
      [`GET ${base}`]: () => ({ status: 200, body: data }),
      [`PATCH ${base}folders/1/`]: () => ({ status: 200, body: {} }),
      [`PATCH ${base}1/`]: () => ({ status: 200, body: {} }),
      [`POST ${base}1/versions/`]: () => ({ status: 201, body: {} }),
      [`DELETE ${base}1/`]: () => ({ status: 204 }),
    })
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Protokolle/ }))
    await user.selectOptions(screen.getByLabelText('Sichtbar für'), 'members')
    await user.click(screen.getByLabelText('Für den Dachverband freigeben (nur lesen)'))
    const folderChanges = calls
      .filter((c) => c.key === `PATCH ${base}folders/1/`)
      .map((c) => JSON.parse(String(c.init?.body)))
    expect(folderChanges).toEqual([{ visibility: 'members' }, { shared_up: true }])
    await user.upload(
      screen.getByLabelText('Neue Fassung von Jahreshauptversammlung'),
      new File(['%PDF'], 'neu.pdf', { type: 'application/pdf' }),
    )
    expect(await screen.findByText('Die neue Fassung wurde hochgeladen.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === `POST ${base}1/versions/`)).toBe(true)
    const item = within(screen.getByText('Jahreshauptversammlung').closest('li')!)
    await user.click(item.getByText('Ältere Fassungen (1)'))
    expect(item.getByRole('link', { name: 'alt.pdf' })).toHaveAttribute(
      'href',
      `${base}versions/11/`,
    )
    await user.click(item.getByRole('button', { name: 'Bearbeiten' }))
    await user.clear(item.getByLabelText('Titel'))
    await user.type(item.getByLabelText('Titel'), 'Neuer Titel')
    await user.click(item.getByRole('button', { name: 'Schließen' }))
    expect(
      calls.some(
        (c) =>
          c.key === `PATCH ${base}1/` && JSON.parse(String(c.init?.body)).title === 'Neuer Titel',
      ),
    ).toBe(true)
    await user.selectOptions(screen.getByLabelText('Jahreshauptversammlung verschieben'), '2')
    expect(await screen.findByText('Das Dokument wurde verschoben.')).toBeInTheDocument()
    expect(
      calls.some(
        (c) => c.key === `PATCH ${base}1/` && JSON.parse(String(c.init?.body)).folder === 2,
      ),
    ).toBe(true)
    // The first delete button is the old version; target the document action explicitly.
    await user.click(item.getAllByRole('button', { name: 'Löschen' }).at(-1)!)
    await user.click(await screen.findByRole('button', { name: 'In den Papierkorb' }))
    expect(await screen.findByText('Das Dokument liegt jetzt im Papierkorb.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === `DELETE ${base}1/`)).toBe(true)
  })

  it('zeigt Budget und Speicherwarnung und behält den Upload bei API-Fehlern', async () => {
    setup(['docs.view', 'docs.manage'], {
      [`GET ${base}`]: () => ({
        status: 200,
        body: { ...overview(), total_bytes: 90, budget_bytes: 100 },
      }),
      [`POST ${base}folders/1/documents/`]: () => ({
        status: 400,
        body: { detail: 'Speicherbudget erschöpft.' },
      }),
    })
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Protokolle/ }))
    expect(screen.getByRole('progressbar', { name: 'Belegter Speicherplatz' })).toHaveAttribute(
      'value',
      '90',
    )
    expect(screen.getByText(/zu über 80 % belegt/)).toBeInTheDocument()
    const file = new File(['%PDF'], 'neu.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Datei für Protokolle'), file)
    await user.click(screen.getByRole('button', { name: 'Hochladen' }))
    expect(await screen.findByText('Speicherbudget erschöpft.')).toBeInTheDocument()
    expect((screen.getByLabelText('Datei für Protokolle') as HTMLInputElement).files?.[0]).toBe(
      file,
    )
  })
})

describe('Explorer in weiteren Bereichen', () => {
  it('zeigt im Mitgliederbereich nur lesbare Dokumente mit Abteilung und Ansichtswechsel', async () => {
    const data = overview(false)
    const portalBase = '/api/portal/5/documents/'
    fakeApi({
      [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: {
          departments: [],
          portal: [
            {
              id: 5,
              club_id: 7,
              club_name: 'Musterverein',
              first_name: 'Erika',
              last_name: 'Muster',
              theme: testOrg().theme,
            },
          ],
        },
      }),
      [`GET ${portalBase}`]: () => ({
        status: 200,
        body: {
          ...data,
          shared: [],
          from_below: [],
          folders: [{ ...data.folders[0], department: 'Musikzug' }],
        },
      }),
    })
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Protokolle.*Musikzug/ }))
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    expect(screen.getByText('Musikzug')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hochladen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Papierkorb' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Listenansicht' }))
    await user.type(screen.getByRole('searchbox'), 'Neuwahlen')
    expect(screen.getByText('Jahreshauptversammlung')).toBeInTheDocument()
    expect(screen.queryByText('Vorstandssitzung')).not.toBeInTheDocument()
  })

  it('behält die Freigabe der Abteilung für den Bürger-Schützenverein bei', async () => {
    const deptBase = '/api/depts/3/documents/'
    const shareLabel = 'Für den Bürger-Schützenverein freigeben (nur lesen)'
    const calls = fakeApi({
      [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: {
          departments: [
            {
              id: 3,
              name: 'Musikzug',
              club_id: 7,
              club_name: 'Musterverein',
              label: 'Zug',
              permissions: ['dept.docs.manage'],
              theme: testOrg().theme,
            },
          ],
          portal: [],
        },
      }),
      [`GET ${deptBase}`]: () => ({
        status: 200,
        body: { ...overview(), share_up_label: shareLabel },
      }),
      [`PATCH ${deptBase}folders/1/`]: () => ({ status: 200, body: {} }),
    })
    renderApp('/dokumente')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Protokolle/ }))
    expect(screen.queryByText('fester Ordner')).not.toBeInTheDocument()
    await user.click(screen.getByLabelText(shareLabel))
    expect(
      calls.some(
        (c) =>
          c.key === `PATCH ${deptBase}folders/1/` && JSON.parse(String(c.init?.body)).shared_up,
      ),
    ).toBe(true)
  })
})
