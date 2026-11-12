import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setCatalogForTest } from '../i18n/index.ts'
import en from '../i18n/en.json'
import { orgApi } from '../api/orgs.ts'
import { ApiError } from '../api/client.ts'
import { memberApi } from '../api/members.ts'
import type { MemberRow } from '../api/members.ts'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const ORG = testOrg({ permissions: ['members.view', 'members.edit'] })
const base = '/api/orgs/7'

const row: MemberRow = {
  id: 11,
  last_name: 'Muster',
  first_name: 'Erika',
  gender: '',
  honorary_titles: [],
  photo_url: null,
  birth_date: '1980-05-17',
  club_number: '1001',
  member_number: 5,
  member_type: 'aktiv',
  status: 'active',
  entry_date: '2015-03-01',
  exit_date: null,
  departments: ['Turnen'],
  email: 'erika@beispiel.test',
  phone: '',
  street: '',
  postal_code: '',
  city: '',
}

function common() {
  return {
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
    [`GET ${base}/member-types/`]: () => ({
      status: 200,
      body: [
        {
          id: 3,
          name: 'aktiv',
          reported: true,
          active: true,
          counts_for_duration: true,
          is_archived: false,
          sort_order: 0,
          in_use: true,
        },
      ],
    }),
    [`GET ${base}/departments/`]: () => ({ status: 200, body: [] }),
    // Ehrungen stehen im Reiter Mitgliedschaft
    [`GET ${base}/honorary-titles/`]: () => ({ status: 200, body: [] }),
  }
}

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

describe('Mitgliederliste', () => {
  it('behält Filter und Seitengröße beim Einklappen und beim erneuten Öffnen der Liste', async () => {
    fakeApi(common())
    const list = vi
      .spyOn(memberApi, 'list')
      .mockResolvedValue({ count: 120, results: [row], next: 'next', previous: null })
    const user = userEvent.setup()
    const view = renderAt('/mitglieder')
    await screen.findByText('Muster, Erika')
    await user.click(screen.getByRole('button', { name: 'Filter (1)' }))
    expect(screen.getByRole('button', { name: 'Filter (1)' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    await user.selectOptions(screen.getByLabelText('Status'), 'ehemalig')
    await user.selectOptions(screen.getByLabelText('Pro Seite'), '10')
    await screen.findByText('Muster, Erika')
    await user.click(screen.getByRole('button', { name: 'Filter (1)' }))
    expect(screen.getByRole('button', { name: 'Filter (1)' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    // Zwei erreichbare Seitennavigationen, oberhalb und unterhalb der Ergebnisse.
    await user.click(screen.getAllByRole('button', { name: 'Nächste Seite' })[0])
    await screen.findByText('Muster, Erika')
    expect(list).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({ status: 'ehemalig', page_size: 10, page: 2 }),
    )
    view.unmount()
    renderAt('/mitglieder')
    await screen.findByText('Muster, Erika')
    expect(screen.getByLabelText('Status')).toHaveValue('ehemalig')
    expect(screen.getByLabelText('Pro Seite')).toHaveValue('10')
    expect(list).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({ status: 'ehemalig', page_size: 10, page: 2 }),
    )
  })

  it('zeigt Mitglieder mit Spalten', async () => {
    fakeApi({
      ...common(),
      [`GET ${base}/members/?status=aktiv&sortierung=name&page=1&page_size=50`]: () => ({
        status: 200,
        body: { count: 1, next: null, previous: null, results: [row] },
      }),
    })
    renderAt('/mitglieder')
    expect(await screen.findByText('Muster, Erika')).toBeInTheDocument()
    expect(screen.getByText('1 Mitglied')).toBeInTheDocument()
    expect(screen.getByText('Turnen')).toBeInTheDocument()
  })
})

describe('Aufnahme', () => {
  it('behält Namen bei fehlgeschlagener Untereinheitenabfrage und lokalem erneutem Laden', async () => {
    fakeApi(common())
    vi.spyOn(orgApi, 'departmentChoices')
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Auswahl unterbrochen.' }))
      .mockResolvedValueOnce([])
    const user = userEvent.setup()
    renderAt('/mitglieder/neu')
    await user.type(await screen.findByLabelText('Name'), 'Muster')
    await screen.findByText(
      'Untereinheiten konnten nicht geladen werden. Deine Eingaben bleiben erhalten.',
    )
    await user.click(screen.getByRole('button', { name: 'Erneut laden' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(screen.getByLabelText('Name')).toHaveValue('Muster')
  })

  it('schlägt Dublette vor und verknüpft', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/duplicates/?name=Muster&vorname=Erika&geburtsdatum=1980-05-17`]:
        () => ({
          status: 200,
          body: [
            {
              id: 42,
              last_name: 'Muster',
              first_name: 'Erika',
              birth_date: '1980-05-17',
              member_number: 5,
              clubs: null,
              already_member_here: false,
            },
          ],
        }),
      [`POST ${base}/members/admit/`]: () => ({ status: 201, body: { id: 99 } }),
      [`GET ${base}/members/99/`]: () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }),
    })
    renderAt('/mitglieder/neu')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Name'), 'Muster')
    await user.type(screen.getByLabelText('Vorname'), 'Erika')
    await user.type(screen.getByLabelText('Geburtsdatum'), '1980-05-17')
    await user.click(screen.getByRole('button', { name: 'Weiter' }))

    expect(await screen.findByRole('heading', { name: 'Mögliche Treffer' })).toHaveFocus()
    await user.click(screen.getByRole('radio', { name: /Verbandsnr\. 5/ }))
    await user.selectOptions(screen.getByLabelText('Mitgliedsart'), '3')
    await user.type(screen.getByLabelText(/E-Mail-Adresse \(optional\)/), 'erika@beispiel.test')
    expect(
      screen.getByText(/Ohne E-Mail erhält das Mitglied Schreiben per Brief/),
    ).toBeInTheDocument()
    await user.type(screen.getByLabelText('Straße und Hausnummer'), 'Weg 1')
    await user.type(screen.getByLabelText('PLZ'), '12345')
    await user.type(screen.getByLabelText('Ort'), 'Musterstadt')
    await user.click(screen.getByRole('button', { name: 'Aufnehmen' }))

    await screen.findByText(/Nicht gefunden|Lädt/)
    const admit = calls.find((c) => c.key === `POST ${base}/members/admit/`)!
    const body = JSON.parse(String(admit.init?.body))
    expect(body.person).toBe(42)
    expect(body.member_type).toBe(3)
    // Die Angaben aus der Suche gehen mit: die ID allein reicht dem Server nicht
    expect(body.last_name).toBe('Muster')
    expect(body.birth_date).toBe('1980-05-17')
  })

  it('nimmt eine Organisation ohne Vorname und Geburtsdatum auf', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/duplicates/?typ=organisation&name=Musterbau+GmbH`]: () => ({
        status: 200,
        body: [],
      }),
      [`POST ${base}/members/admit/`]: () => ({ status: 201, body: { id: 99 } }),
      [`GET ${base}/members/99/`]: () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }),
    })
    renderAt('/mitglieder/neu')
    const user = userEvent.setup()
    const organisation = await screen.findByRole('button', {
      name: 'eine Organisation (Firma, Verein, Behörde …)',
    })
    expect(screen.getByRole('button', { name: 'eine Person' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(organisation)
    expect(organisation).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByLabelText('Vorname')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Geburtsdatum')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Name der Organisation'), 'Musterbau GmbH')
    await user.selectOptions(screen.getByLabelText('Rechtsform (optional)'), 'gmbh')
    await user.click(screen.getByRole('button', { name: 'Weiter' }))

    await screen.findByRole('heading', { name: '2. Mitgliedschaft und Kontakt' })
    await user.selectOptions(screen.getByLabelText('Mitgliedsart'), '3')
    await user.type(screen.getByLabelText('USt-IdNr.'), 'DE123456789')
    await user.type(screen.getByLabelText('Straße und Hausnummer'), 'Musterstraße 1')
    await user.type(screen.getByLabelText('PLZ'), '12345')
    await user.type(screen.getByLabelText('Ort'), 'Musterstadt')
    await user.click(screen.getByRole('button', { name: 'Aufnehmen' }))

    await screen.findByText(/Nicht gefunden|Lädt/)
    const admit = calls.find((c) => c.key === `POST ${base}/members/admit/`)!
    const body = JSON.parse(String(admit.init?.body))
    expect(body.kind).toBe('organization')
    expect(body.last_name).toBe('Musterbau GmbH')
    expect(body.legal_form).toBe('gmbh')
    expect(body.vat_id).toBe('DE123456789')
  })
})

const detail = {
  id: 11,
  person_id: 42,
  last_name: 'Muster',
  first_name: 'Erika',
  birth_date: '1980-05-17',
  club_number: '',
  contact: {
    email: 'e@beispiel.test',
    phone: '',
    street: 'Weg 1',
    postal_code: '1',
    city: 'x',
    country: 'Deutschland',
  },
  contact_shared: true,
  status: 'active',
  current_type: {
    id: 1,
    member_type: 3,
    member_type_name: 'aktiv',
    active: true,
    reported: true,
    valid_from: '2015-03-01',
    valid_until: null,
  },
  periods: [
    {
      id: 5,
      entry_date: '2015-03-01',
      exit_date: null,
      exit_reason: '',
      exit_reason_label: '',
      note: '',
    },
  ],
  type_history: [],
  departments: [],
  department_roles: [],
  board_roles: [],
  federation: null,
  exit_reasons: [
    { value: 'exit', label: 'Austritt' },
    { value: 'death', label: 'Tod' },
  ],
  purged: false,
  purge_due: null,
  duration: { club: { days: 3000, years: 8, next: null }, federation: null },
  photo: { approved: null, pending: null },
  photo_consent_at: null,
  photo_consent_source: '',
  other_memberships: null,
}

describe('Mitgliedsakte', () => {
  const department = {
    id: 21,
    department: 4,
    department_name: 'HFC',
    valid_from: '2015-03-01',
    valid_until: '2020-12-31' as string | null,
  }
  const editName = 'Mitgliedschaft in HFC bearbeiten'
  const departmentUrl = `${base}/members/11/departments/21/`

  it.each([['2020-12-31'], [null]])(
    'korrigiert Beginn und Ende einer Zugmitgliedschaft (bisheriges Ende: %s)',
    async (valid_until) => {
      let membership = { ...department, valid_until }
      const calls = fakeApi({
        ...common(),
        [`GET ${base}/members/11/`]: () => ({
          status: 200,
          body: { ...detail, departments: [membership] },
        }),
        [`PATCH ${departmentUrl}`]: (init) => {
          membership = { ...membership, ...JSON.parse(String(init?.body)) }
          return { status: 200, body: membership }
        },
      })
      const user = userEvent.setup()
      renderAt('/mitglieder/11?bereich=mitgliedschaft')
      await user.click(await screen.findByRole('button', { name: editName }))
      const form = within(screen.getByRole('form', { name: editName }))
      expect(form.getByLabelText('Beginn')).toHaveValue('2015-03-01')
      expect(form.getByLabelText('Ende')).toHaveValue(valid_until ?? '')
      fireEvent.change(form.getByLabelText('Beginn'), { target: { value: '2014-01-01' } })
      fireEvent.change(form.getByLabelText('Ende'), { target: { value: '2021-12-31' } })
      await user.click(form.getByRole('button', { name: 'Speichern' }))
      await waitFor(() => expect(screen.queryByRole('form', { name: editName })).toBeNull())
      const patch = calls.find((c) => c.key === `PATCH ${departmentUrl}`)!
      expect(JSON.parse(String(patch.init?.body))).toEqual({
        valid_from: '2014-01-01',
        valid_until: '2021-12-31',
      })
      // Die Akte wurde neu geladen; erneutes Öffnen zeigt die gespeicherte Korrektur.
      await user.click(screen.getByRole('button', { name: editName }))
      expect(screen.getByLabelText('Beginn')).toHaveValue('2014-01-01')
      expect(screen.getByLabelText('Ende')).toHaveValue('2021-12-31')
    },
  )

  it('behält Eingaben bei Überschneidungen und kann ein Ende wieder entfernen', async () => {
    let reject = true
    let membership = { ...department }
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, departments: [membership] },
      }),
      [`PATCH ${departmentUrl}`]: (init) => {
        if (reject) {
          return {
            status: 400,
            body: { non_field_errors: ['Ein Mitglied darf nur einem Zug gleichzeitig angehören.'] },
          }
        }
        membership = { ...membership, ...JSON.parse(String(init?.body)) }
        return { status: 200, body: membership }
      },
    })
    const user = userEvent.setup()
    renderAt('/mitglieder/11?bereich=mitgliedschaft')
    await user.click(await screen.findByRole('button', { name: editName }))
    fireEvent.change(screen.getByLabelText('Beginn'), { target: { value: '2014-01-01' } })
    await user.clear(screen.getByLabelText('Ende'))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ein Mitglied darf nur einem Zug gleichzeitig angehören.',
    )
    expect(screen.getByLabelText('Beginn')).toHaveValue('2014-01-01')
    expect(screen.getByLabelText('Ende')).toHaveValue('')
    reject = false
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(screen.queryByRole('form', { name: editName })).toBeNull())
    const patch = calls.filter((c) => c.key === `PATCH ${departmentUrl}`).at(-1)!
    expect(JSON.parse(String(patch.init?.body))).toEqual({
      valid_from: '2014-01-01',
      valid_until: null,
    })
  })

  it('trägt einen früheren, aufgelösten Zug mit Ende in einem Schritt nach', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, departments: [department] },
      }),
      [`GET ${base}/department-choices/`]: () => ({
        status: 200,
        body: [
          {
            id: 5,
            name: 'Alter Zug',
            short_name: '',
            display_name: 'Alter Zug',
            is_active: false,
            parent_unit: null,
            depth: 0,
            path: '',
            roles: [],
          },
        ],
      }),
      [`POST ${base}/members/11/departments/`]: (init) => ({
        status: 201,
        body: { id: 22, department_name: 'Alter Zug', ...JSON.parse(String(init?.body)) },
      }),
    })
    const user = userEvent.setup()
    renderAt('/mitglieder/11?bereich=mitgliedschaft')
    await user.selectOptions(
      await screen.findByRole('combobox', { name: 'Abteilung hinzufügen' }),
      '5',
    )
    expect(screen.getByRole('option', { name: 'Alter Zug (inaktiv)' })).toBeInTheDocument()
    expect(screen.getByLabelText('bis (leer = heute)')).toBeRequired()
    fireEvent.change(screen.getByLabelText('ab'), { target: { value: '2010-01-01' } })
    fireEvent.change(screen.getByLabelText('bis (leer = heute)'), {
      target: { value: '2015-02-28' },
    })
    await user.click(screen.getByRole('button', { name: 'Hinzufügen' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === `POST ${base}/members/11/departments/`)).toBe(true),
    )
    const post = calls.find((c) => c.key === `POST ${base}/members/11/departments/`)!
    expect(JSON.parse(String(post.init?.body))).toEqual({
      department: 5,
      valid_from: '2010-01-01',
      valid_until: '2015-02-28',
    })
  })

  it('fragt beim Abbrechen einer Korrektur vor dem Verwerfen und speichert nichts', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, departments: [department] },
      }),
    })
    const user = userEvent.setup()
    renderAt('/mitglieder/11?bereich=mitgliedschaft')
    await user.click(await screen.findByRole('button', { name: editName }))
    fireEvent.change(screen.getByLabelText('Beginn'), { target: { value: '2014-01-01' } })
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Verwerfen' }))
    expect(screen.queryByRole('form', { name: editName })).not.toBeInTheDocument()
    expect(calls.some((c) => c.key.startsWith('PATCH '))).toBe(false)
    await user.click(screen.getByRole('button', { name: editName }))
    expect(screen.getByLabelText('Beginn')).toHaveValue(department.valid_from)
  })

  it('bietet die Zeitkorrektur nur mit Mitgliederschreibrecht an', async () => {
    fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['members.view'] })],
      }),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, departments: [department] },
      }),
    })
    renderAt('/mitglieder/11?bereich=mitgliedschaft')
    await screen.findByText('HFC')
    expect(screen.queryByRole('button', { name: editName })).not.toBeInTheDocument()
  })

  it('fern geführt: Stammdaten gesperrt, Korrektur vorschlagen', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, managed_by: { id: 3, name: 'Jägerzug' } },
      }),
      [`POST ${base}/peering/members/11/suggest/`]: () => ({ status: 202, body: {} }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    expect(
      await screen.findByText(/pflegt Jägerzug auf einer eigenen HUBIplan-Instanz/),
    ).toBeInTheDocument()
    expect(screen.getAllByLabelText(/^Vorname/)[0]).toBeDisabled()
    const fields = screen.getAllByLabelText(/^Vorname/)
    await user.clear(fields[1])
    await user.type(fields[1], 'Erica')
    await user.click(screen.getByRole('button', { name: 'Korrektur vorschlagen' }))
    expect(await screen.findByText('Der Vorschlag ist an Jägerzug unterwegs.')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${base}/peering/members/11/suggest/`)
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ first_name: 'Erica' })
  })

  it('zeigt Stammdaten zuerst und Foto im eigenen Bereich (S-03)', async () => {
    fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({ status: 200, body: detail }),
      [`GET ${base}/members/11/photo-links/`]: () => ({ status: 200, body: [] }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { level: 2, name: 'Stammdaten' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Foto' })).not.toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Bereiche der Mitgliedsakte' })
    const names = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent)
    expect(names[0]).toBe('Stammdaten')
    expect(names).toContain('Foto & Webseite')
    // Ohne Musikmodul kein Reiter „Musik“ und kein Link in den Musikbereich
    expect(names).not.toContain('Musik')
    expect(names.indexOf('Foto & Webseite')).toBeLessThan(names.indexOf('Verlauf'))
    // Handy: Auswahlliste mit denselben Bereichen
    await user.selectOptions(screen.getByLabelText('Bereich'), 'foto')
    expect(await screen.findByRole('heading', { name: 'Foto' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Stammdaten' })).not.toBeInTheDocument()
  })

  it('Auf einen Blick: Kacheln nur mit Inhalt und Recht (S-03 A3)', async () => {
    const glanceOrg = testOrg({
      permissions: ['members.view', 'billing.view', 'logins.view'],
      modules: ['members', 'billing'],
    })
    fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({ status: 200, body: [glanceOrg] }),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: {
          ...detail,
          summary: {
            invoices: { open: 1, open_amount: '25.00', overdue: 1 },
            account: { has_access: true, last_login: null, mfa: true, app: false },
          },
        },
      }),
    })
    renderAt('/mitglieder/11')
    const glance = await screen.findByRole('region', { name: 'Auf einen Blick' })
    expect(within(glance).getByRole('heading', { name: 'Mitglied seit' })).toBeInTheDocument()
    const fees = within(glance).getByRole('link', { name: /^Beiträge/ })
    expect(fees).toHaveAttribute('href', '/mitglieder/11?bereich=beitraege')
    expect(fees).toHaveTextContent('1 Rechnung offen · davon 1 überfällig')
    const account = within(glance).getByRole('link', { name: /^Konto/ })
    expect(account).toHaveTextContent('Zwei-Faktor an')
    expect(account).toHaveTextContent('Noch nie angemeldet')
    // Ohne Materialmodul keine Materialkachel
    expect(within(glance).queryByRole('heading', { name: 'Material' })).not.toBeInTheDocument()
  })

  it('Auf einen Blick: ohne Zusammenfassung keine Beitrags- und Kontokachel', async () => {
    fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, summary: { invoices: null, account: null } },
      }),
    })
    renderAt('/mitglieder/11')
    const glance = await screen.findByRole('region', { name: 'Auf einen Blick' })
    expect(within(glance).queryByRole('link', { name: /^Beiträge/ })).not.toBeInTheDocument()
    expect(within(glance).queryByRole('link', { name: /^Konto/ })).not.toBeInTheDocument()
  })

  it('Kopf: Name als Überschrift, E-Mail und weitere Aktionen (S-03 A2)', async () => {
    fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({ status: 200, body: detail }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Erika Muster' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Mitglied · aktiv')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'E-Mail' })).toHaveAttribute(
      'href',
      'mailto:e@beispiel.test',
    )
    // Ohne Telefonnummer kein „Anrufen“
    expect(screen.queryByRole('link', { name: 'Anrufen' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Weitere Aktionen/ }))
    expect(screen.getByRole('link', { name: 'Austritt erfassen' })).toHaveAttribute(
      'href',
      '/mitglieder/11?bereich=mitgliedschaft',
    )
  })

  it('erfasst einen Austritt', async () => {
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({ status: 200, body: detail }),
      [`POST ${base}/members/11/exit/`]: () => ({
        status: 200,
        body: { ...detail, status: 'former', purge_due: '2026-12-31' },
      }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: 'Mitgliedschaft' }))
    await user.click(await screen.findByRole('button', { name: 'Austritt erfassen' }))
    await user.selectOptions(screen.getByLabelText('Grund'), 'death')
    await user.click(screen.getByRole('button', { name: 'Austritt speichern' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Austritt erfassen' }))
    expect(await screen.findByRole('button', { name: 'Wiedereintritt' })).toBeInTheDocument()
    expect(screen.getByText(/31\.12\.2026/)).toBeInTheDocument()
    const call = calls.find((c) => c.key === `POST ${base}/members/11/exit/`)!
    expect(JSON.parse(String(call.init?.body)).exit_reason).toBe('death')
  })

  it('Organisation: Ansprechpartner hinzufügen', async () => {
    const contact = {
      id: 5,
      linked_member: null,
      display_name: 'Max Muster',
      last_name: 'Muster',
      first_name: 'Max',
      gender: '',
      function: 'Geschäftsführer',
      email: 'max@musterbau.example',
      phone: '',
      contact_email: 'max@musterbau.example',
      contact_phone: '',
      is_primary: true,
      receives_mail: true,
      receives_invoices: true,
      represents: true,
      member_access: false,
      since: null,
    }
    const firma = {
      ...detail,
      kind: 'organization',
      last_name: 'Musterbau GmbH',
      first_name: '',
      birth_date: null,
      organization: {
        name_suffix: '',
        legal_form: 'gmbh',
        legal_form_label: 'GmbH',
        legal_form_other: '',
        register: '',
        vat_id: '',
        website: '',
        size: null,
      },
      contact_persons: [],
    }
    let saved = false
    const calls = fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...firma, contact_persons: saved ? [contact] : [] },
      }),
      [`POST ${base}/members/11/contacts/`]: () => {
        saved = true
        return { status: 201, body: contact }
      },
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    expect(await screen.findByText('Noch kein Ansprechpartner eingetragen.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ansprechpartner hinzufügen' }))
    const section = screen.getByRole('region', { name: 'Ansprechpartner' })
    await user.type(within(section).getByRole('textbox', { name: /^Name/ }), 'Muster')
    await user.type(within(section).getByLabelText(/^Vorname/), 'Max')
    await user.type(within(section).getByLabelText(/^Funktion/), 'Geschäftsführer')
    expect(within(section).getByLabelText('Hauptansprechpartner')).toBeChecked()
    await user.click(within(section).getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText('Max Muster')).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${base}/members/11/contacts/`)
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      last_name: 'Muster',
      first_name: 'Max',
      function: 'Geschäftsführer',
      is_primary: true,
      member: null,
    })
  })

  it('Organisation: Mitgliederbereich je Ansprechpartner', async () => {
    const contact = {
      id: 5,
      linked_member: null,
      display_name: 'Max Muster',
      last_name: 'Muster',
      first_name: 'Max',
      gender: '',
      function: '',
      email: 'max@musterbau.example',
      phone: '',
      contact_email: 'max@musterbau.example',
      contact_phone: '',
      is_primary: true,
      receives_mail: true,
      receives_invoices: true,
      represents: true,
      member_access: false,
      since: null,
    }
    const firma = {
      ...detail,
      kind: 'organization',
      last_name: 'Musterbau GmbH',
      first_name: '',
      birth_date: null,
      organization: {
        name_suffix: '',
        legal_form: 'gmbh',
        legal_form_label: 'GmbH',
        legal_form_other: '',
        register: '',
        vat_id: '',
        website: '',
        size: null,
      },
      contact_persons: [contact],
    }
    const access = `${base}/members/11/access/?ansprechpartner=5`
    const withLogins = testOrg({
      permissions: ['members.view', 'members.edit', 'logins.view', 'logins.edit'],
    })
    const calls = fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({ status: 200, body: [withLogins] }),
      [`GET ${base}/members/11/`]: () => ({ status: 200, body: firma }),
      [`GET ${access}`]: () => ({
        status: 200,
        body: { access: null, portal_enabled: true, department_access_enabled: false },
      }),
      [`POST ${access}`]: () => ({
        status: 200,
        body: {
          access: {
            email: 'max@musterbau.example',
            created_at: '2026-11-06T20:00:00Z',
            last_login: null,
            login: 'link',
          },
          sent: 'link',
        },
      }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: 'Rollen und Konto' }))
    expect(
      await screen.findByRole('heading', { name: 'Mitgliederbereich für Max Muster' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Freischalten und Anmeldelink senden' }))
    expect(await screen.findByText('Anmeldelink per E-Mail gesendet.')).toBeInTheDocument()
    expect(calls.some((c) => c.key === `POST ${access}`)).toBe(true)
    expect(calls.some((c) => c.key === `GET ${base}/members/11/access/`)).toBe(false)
  })

  it('Rechnungsanschrift festlegen', async () => {
    const billingOrg = testOrg({
      permissions: ['members.view', 'members.edit'],
      modules: ['members', 'billing'],
    })
    const address = {
      name: 'Musterbau Holding AG',
      attention: 'Buchhaltung',
      street: 'Postfach 10 20 30',
      postal_code: '54321',
      city: 'Beispielstadt',
      country: '',
      email: 'rechnung@musterbau.example',
      order_reference: '',
      leitweg_id: '991-12345-67',
    }
    const calls = fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({ status: 200, body: [billingOrg] }),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, billing_address: null },
      }),
      [`PUT ${base}/members/11/billing-address/`]: () => ({
        status: 200,
        body: { ...detail, billing_address: address },
      }),
    })
    renderAt('/mitglieder/11?bereich=beitraege')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Rechnungsanschrift festlegen' }))
    const section = screen.getByRole('region', { name: 'Rechnungsanschrift' })
    await user.type(within(section).getByLabelText(/^Straße oder Postfach/), address.street)
    await user.type(within(section).getByLabelText(/^PLZ/), address.postal_code)
    await user.type(within(section).getByLabelText(/^Ort/), address.city)
    await user.type(within(section).getByLabelText(/^Leitweg-ID/), address.leitweg_id)
    await user.click(within(section).getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/Leitweg-ID: 991-12345-67/)).toBeInTheDocument()
    const put = calls.find((c) => c.key === `PUT ${base}/members/11/billing-address/`)
    expect(JSON.parse(String(put?.init?.body))).toMatchObject({
      street: 'Postfach 10 20 30',
      city: 'Beispielstadt',
      leitweg_id: '991-12345-67',
    })
  })

  it('Beiträge: Rechnungen und offene Beträge des Mitglieds', async () => {
    const billingOrg = testOrg({
      permissions: ['members.view', 'billing.view'],
      modules: ['members', 'billing'],
    })
    fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({ status: 200, body: [billingOrg] }),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: { ...detail, billing_address: null },
      }),
      [`GET ${base}/billing/invoices/?mitglied=11`]: () => ({
        status: 200,
        body: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 5,
              number: 'R-2026-7',
              date: '2026-01-15',
              subject: 'Jahresbeitrag 2026',
              total: '60.00',
              outstanding: '60.00',
              status: 'open',
              status_label: 'offen',
              overdue: true,
            },
          ],
        },
      }),
    })
    renderAt('/mitglieder/11?bereich=beitraege')
    expect(await screen.findByRole('link', { name: 'R-2026-7' })).toHaveAttribute(
      'href',
      '/finanzen/rechnungen?rechnung=5',
    )
    expect(screen.getByText(/Offen: 60,00/)).toBeInTheDocument()
  })

  it('nennt den Namen des Dachverbands nur einmal', async () => {
    fakeApi({
      ...common(),
      [`GET ${base}/members/11/`]: () => ({
        status: 200,
        body: {
          ...detail,
          federation: {
            name: 'Testbund von 1855 e.V.',
            is_member: true,
            member_number: 1,
            entry_date: '2007-01-01',
            entry_date_manual: false,
          },
        },
      }),
    })
    renderAt('/mitglieder/11')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: 'Mitgliedschaft' }))
    expect(
      await screen.findByRole('heading', { name: 'Testbund von 1855 e.V.' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Mitglied')).toBeInTheDocument()
    // Die Verbandsnummer steht in der Akte nicht (weder im Kopf noch beim Dachverband).
    expect(screen.queryByText(/Verbandsnr\./)).not.toBeInTheDocument()
    expect(screen.getByText(/^Eintritt:/)).toHaveTextContent(/\(berechnet\)$/)
    expect(screen.queryByText(/Mitglied im|Eintritt in/)).not.toBeInTheDocument()
  })
})

describe('Export', () => {
  it('exportiert die gefilterte Liste mit gewählten Spalten', async () => {
    const org = testOrg({ permissions: ['members.view', 'export.run'] })
    const calls = fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${base}/members/?status=aktiv&sortierung=name&page=1&page_size=50`]: () => ({
        status: 200,
        body: { count: 1, next: null, previous: null, results: [row] },
      }),
      [`GET ${base}/export-columns/`]: () => ({
        status: 200,
        body: {
          members: [
            { key: 'last_name', label: 'Name' },
            { key: 'first_name', label: 'Vorname' },
            { key: 'email', label: 'E-Mail' },
          ],
          jubilees: [],
        },
      }),
      [`GET ${base}/export-templates/`]: () => ({ status: 200, body: [] }),
      [`POST ${base}/exports/`]: () => ({ status: 201, body: { id: 5, status: 'pending' } }),
      [`GET ${base}/exports/5/`]: () => ({
        status: 200,
        body: { id: 5, status: 'done', row_count: 1, file_name: 'Mitgliederliste.xlsx' },
      }),
    })
    renderAt('/mitglieder')
    const user = userEvent.setup()
    await screen.findByText('Muster, Erika')
    // Export steht im Seitenkopf unter „Weitere Aktionen“ (S-05)
    await user.click(screen.getByRole('button', { name: 'Weitere Aktionen' }))
    await user.click(screen.getByRole('button', { name: 'Export' }))
    await user.click(await screen.findByRole('checkbox', { name: 'E-Mail' }))
    await user.click(screen.getByRole('button', { name: 'Export erstellen' }))
    expect(await screen.findByRole('link', { name: /Mitgliederliste.xlsx/ })).toHaveAttribute(
      'href',
      `${base}/exports/5/download/`,
    )
    const post = calls.find((c) => c.key === `POST ${base}/exports/`)!
    const body = JSON.parse(String(post.init?.body))
    expect(body.columns).toEqual(['last_name', 'first_name'])
    expect(body.filters.status).toBe('aktiv')
  })
})

describe('Dachverband', () => {
  it('zeigt Mitglieder aller Vereine nur mit Freigabe', async () => {
    const fed = testOrg({
      id: 2,
      name: 'Testbund',
      type: 'federation',
      type_label: 'Dachverband',
      parent_name: null,
      permissions: ['members.view'],
      modules: ['members'],
      federation_member_access: 'read',
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [fed] }),
      'GET /api/orgs/2/federation/clubs/': () => ({
        status: 200,
        body: [{ id: 7, name: 'TV Beispielhausen' }],
      }),
      'GET /api/orgs/2/federation/members/?status=aktiv&sortierung=name&page=1&page_size=50':
        () => ({
          status: 200,
          body: {
            count: 1,
            next: null,
            previous: null,
            results: [{ ...row, club: 'TV Beispielhausen', club_id: 7 }],
          },
        }),
    })
    renderAt('/mitglieder')
    expect(await screen.findByText('Muster, Erika')).toBeInTheDocument()
    // h1 = Menüpunkt (Seitenkopf S-05)
    expect(screen.getByRole('heading', { level: 1, name: 'Mitglieder' })).toBeInTheDocument()
    expect(screen.getByText(/nur lesen/)).toBeInTheDocument()
  })

  it('ohne Freigabe kein Menüpunkt Mitglieder', async () => {
    const fed = testOrg({
      id: 2,
      name: 'Testbund',
      type: 'federation',
      federation_member_access: 'none',
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [fed] }),
    })
    renderAt('/')
    await screen.findByRole('heading', { name: 'Testbund' })
    expect(screen.getByRole('navigation', { name: 'Module' })).not.toHaveTextContent('Mitglieder')
  })
})

describe('Foto-Upload-Link', () => {
  it('zeigt nur Vorname und Verein', async () => {
    fakeApi({
      [SESSION]: () => ({ status: 401, body: { status: 401, data: { flows: [] } } }),
      'GET /api/public/photo/abc123/': () => ({
        status: 200,
        body: {
          first_name: 'Erika',
          organization: 'TV Beispielhausen',
          logo_url: null,
          theme: {
            primary: '#123e7a',
            on_primary: '#ffffff',
            accent: '#e0a526',
            on_accent: '#1d2421',
          },
          expires_at: '2026-11-07T12:00:00Z',
          needs_approval: false,
        },
      }),
    })
    renderAt('/foto/abc123')
    expect(await screen.findByRole('heading', { name: 'Hallo Erika!' })).toBeInTheDocument()
    expect(screen.getByText(/Ich willige ein, dass TV Beispielhausen/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Foto hochladen' })).toBeDisabled()
  })

  it('meldet ungültige Links', async () => {
    fakeApi({
      [SESSION]: () => ({ status: 401, body: { status: 401, data: { flows: [] } } }),
      'GET /api/public/photo/alt/': () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }),
    })
    renderAt('/foto/alt')
    expect(await screen.findByText(/nicht \(mehr\) gültig/)).toBeInTheDocument()
  })
})

describe('Aufnahme mit nachvollziehbarem Fokus und Feldgruppen', () => {
  afterEach(() => setCatalogForTest('de'))
  const search =
    'GET /api/orgs/7/members/duplicates/?name=Muster&vorname=Erika&geburtsdatum=1980-05-17'
  const departments = [
    {
      id: 2,
      name: 'Turnen',
      display_name: 'Turnen',
      short_name: '',
      is_active: true,
      depth: 0,
      path: 'Turnen',
    },
  ]
  it('benennt die Gruppe mit den englischen Untereinheitsbegriffen des Vereins', async () => {
    setCatalogForTest('en', en)
    fakeApi({
      ...common(),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [{ ...ORG, department_terms: { Pl: 'Teams', pl: 'teams' } }],
      }),
      [search]: () => ({ status: 200, body: [] }),
      'GET /api/orgs/7/departments/': () => ({ status: 200, body: departments }),
    })
    renderAt('/mitglieder/neu')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Name'), 'Muster')
    await user.type(screen.getByLabelText('First name'), 'Erika')
    await user.type(screen.getByLabelText('Date of birth'), '1980-05-17')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('group', { name: 'Teams (optional)' })).toBeVisible()
  })
  async function firstStep() {
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Name'), 'Muster')
    await user.type(screen.getByLabelText('Vorname'), 'Erika')
    await user.type(screen.getByLabelText('Geburtsdatum'), '1980-05-17')
    await user.click(screen.getByRole('button', { name: 'Weiter' }))
    return user
  }
  it('fokussiert die neue Stufe und beim Zurückgehen wieder die erhaltene Eingabe', async () => {
    fakeApi({ ...common(), [search]: () => ({ status: 200, body: [] }) })
    renderAt('/mitglieder/neu')
    const user = await firstStep()
    expect(
      await screen.findByRole('heading', { name: '2. Mitgliedschaft und Kontakt' }),
    ).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'ändern' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'ändern' }))
    expect(screen.getByLabelText('Name')).toHaveFocus()
    expect(screen.getByLabelText('Name')).toHaveValue('Muster')
    expect(screen.getByLabelText('Vorname')).toHaveValue('Erika')
  })
  it('verbindet Gruppenname und Serverfehler mit den Untereinheiten und fokussiert die Fehlergruppe', async () => {
    fakeApi({
      ...common(),
      [search]: () => ({ status: 200, body: [] }),
      'GET /api/orgs/7/departments/': () => ({ status: 200, body: departments }),
      'POST /api/orgs/7/members/admit/': () => ({
        status: 400,
        body: { department_ids: ['Diese Einheit ist nicht freigegeben.'] },
      }),
    })
    renderAt('/mitglieder/neu')
    const user = await firstStep()
    const group = await screen.findByRole('group', { name: 'Abteilungen (optional)' })
    await user.click(within(group).getByRole('checkbox', { name: 'Turnen' }))
    await user.selectOptions(screen.getByLabelText('Mitgliedsart'), '3')
    await user.type(screen.getByLabelText('Straße und Hausnummer'), 'Musterweg 1')
    await user.type(screen.getByLabelText('PLZ'), '12345')
    await user.type(screen.getByLabelText('Ort'), 'Musterstadt')
    await user.click(screen.getByRole('button', { name: 'Aufnehmen' }))
    await waitFor(() => expect(group).toHaveFocus())
    expect(group).toHaveAccessibleDescription('Diese Einheit ist nicht freigegeben.')
    expect(within(group).getByRole('checkbox', { name: 'Turnen' })).toBeChecked()
  })
})
