import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

const context = {
  key: 'org:7',
  organization: { id: 7, name: 'TV Beispielhausen', type: 'club' },
  units: [
    {
      id: 7,
      name: 'TV Beispielhausen',
      is_self: true,
      contact: { email: 'info@tv.example.org', phone: '0123 4' },
    },
    { id: 9, name: 'Jägerzug', is_self: false, contact: { email: '', phone: '' } },
  ],
  functions: [{ key: 'role:3', name: 'Kassierer', contact_email: 'kasse@tv.example.org' }],
  name: 'Karla Kasse',
  own: { email: 'karla.privat@example.org', phone: '0170 1', address: ['Weg 1', '12345 Ort'] },
}

const letterhead = {
  organization: { id: 7, name: 'TV Beispielhausen', type: 'club' },
  letterhead: {
    mode: 'own',
    form: 'b',
    logo_position: 'right',
    tagline: 'gegründet 1900',
    font: 'Arial',
    salutation: 'Sehr geehrte Damen und Herren,',
    closing: 'Mit freundlichen Grüßen',
    show_bank: true,
    account: null,
    show_email: true,
    show_phone: true,
    show_website: true,
    show_board: true,
    show_register: true,
    show_social: false,
    heading_font: '',
    font_fallback: 'Arial',
    heading_font_fallback: 'Georgia',
    show_name: true,
    head_name: '',
    head_name_small: false,
    logo_size: 'medium',
    line_color: '1',
    head_line: true,
    footer_line: true,
    title_color: 'black',
    table_line_color: '0',
    table_stripe: 'grey',
    updated_at: '2026-10-28T10:00:00Z',
  },
  may_have_own: true,
  owner: { id: 7, name: 'TV Beispielhausen', is_self: true },
  accounts: [{ id: 1, name: 'Girokonto', iban: 'DE89 3704', bank: 'Musterbank' }],
  board: [{ name: 'Vera Vorsitz', role: '1. Vorsitzende' }],
  palette: [
    { slot: 0, color: '#1d5c3a', contrast: 7.9 },
    { slot: 1, color: '#fbc707', contrast: 1.6 },
  ],
  hints: [],
}

function show(path: string, routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg()] }),
    ...routes,
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
  return calls
}

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), writable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
})

describe('Briefvorlage erstellen', () => {
  it('wählt private Angaben nie vor und lädt mit den gewählten Kontaktwegen', async () => {
    const calls = show('/briefvorlage', {
      'GET /api/me/letterheads/': () => ({
        status: 200,
        body: { contexts: [context], choices: [], notices: [] },
      }),
      'POST /api/me/letterheads/download/': () => ({ status: 200, body: 'PK' }),
    })
    const user = userEvent.setup()
    const unitBox = await screen.findByRole('checkbox', { name: /Kontakt der Einheit/ })
    expect(unitBox).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Funktionsadresse/ })).toBeChecked()
    const privateMail = screen.getByRole('checkbox', { name: /Meine E-Mail-Adresse/ })
    expect(privateMail).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Meine Telefonnummer/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Meine Anschrift/ })).not.toBeChecked()
    await user.click(privateMail)
    expect(screen.getByText(/Deine privaten Angaben stehen dann/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Herunterladen' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/me/letterheads/download/')).toBe(true),
    )
    const sent = calls.find((c) => c.key === 'POST /api/me/letterheads/download/')!
    const body = sent.init!.body as FormData
    expect(body.get('contacts')).toBe('unit,role,own_email')
    expect(body.get('unit')).toBe('7')
    expect(body.get('format')).toBe('dotx')
    expect(await screen.findByText(/Die Vorlage ist heruntergeladen/)).toBeInTheDocument()
  })

  it('steht als Rundschreiben › Brief im Menü', async () => {
    show('/rundschreiben/brief', {
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['circulars.view', 'circulars.send'] })],
      }),
      'GET /api/me/letterheads/': () => ({
        status: 200,
        body: { contexts: [context], choices: [], notices: [] },
      }),
    })
    expect(await screen.findByRole('heading', { name: 'Brief', level: 1 })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Herunterladen' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Brief' })).toHaveAttribute(
      'href',
      '/rundschreiben/brief',
    )
  })

  it('sagt ohne Funktion, wer Vorlagen erstellt', async () => {
    show('/briefvorlage', {})
    expect(await screen.findByText(/Du hast gerade keine solche Funktion/)).toBeInTheDocument()
  })

  it('zeigt auf der Startseite den Hinweis „veraltet“ und blendet ihn aus', async () => {
    let notices = [
      {
        kind: 'outdated',
        unit: { id: 7, name: 'TV Beispielhausen' },
        context: 'org:7',
        changes: ['Bankverbindung'],
      },
    ]
    const calls = show('/', {
      'GET /api/me/letterheads/': () => ({
        status: 200,
        body: { contexts: [context], choices: [], notices },
      }),
      'POST /api/me/letterheads/dismiss/': () => {
        notices = []
        return { status: 204 }
      },
    })
    const user = userEvent.setup()
    expect(
      await screen.findByText(/Deine Briefvorlage für TV Beispielhausen ist veraltet/),
    ).toHaveTextContent('Bankverbindung geändert')
    await user.click(screen.getByRole('button', { name: 'Später' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/me/letterheads/dismiss/')).toBe(true),
    )
    await waitFor(() => expect(screen.queryByText(/ist veraltet/)).not.toBeInTheDocument())
  })
})

describe('Einstellungen › Briefbogen', () => {
  it('speichert Änderungen automatisch und zeigt den Vorstand', async () => {
    const calls = show('/einstellungen/briefbogen', {
      'GET /api/orgs/7/letterhead/': () => ({ status: 200, body: letterhead }),
      'GET /api/orgs/7/letterhead/preview/': () => ({ status: 200, body: '%PDF' }),
      'PATCH /api/orgs/7/letterhead/': (init) => ({
        status: 200,
        body: {
          ...letterhead,
          letterhead: { ...letterhead.letterhead, ...JSON.parse(String(init?.body)) },
        },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText(/Heute: Vera Vorsitz \(1\. Vorsitzende\)/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(/^Schrift für den Text/), 'Georgia')
    await waitFor(
      () => {
        const patch = calls.find((c) => c.key === 'PATCH /api/orgs/7/letterhead/')
        expect(patch && JSON.parse(String(patch.init?.body))).toEqual({ font: 'Georgia' })
      },
      { timeout: 3000 },
    )
    expect(await screen.findByTitle('Vorschau der ersten Seite')).toBeInTheDocument()
    expect(screen.getByTitle('Vorschau der ersten Seite')).toHaveAttribute(
      'src',
      'blob:x#view=Fit&zoom=page-fit',
    )
  })

  it('stellt Linienfarbe, Logogröße und Schriften ein (Issue #470)', async () => {
    const calls = show('/einstellungen/briefbogen', {
      'GET /api/orgs/7/letterhead/': () => ({ status: 200, body: letterhead }),
      'GET /api/orgs/7/letterhead/preview/': () => ({ status: 200, body: '%PDF' }),
      'PATCH /api/orgs/7/letterhead/': (init) => ({
        status: 200,
        body: {
          ...letterhead,
          letterhead: { ...letterhead.letterhead, ...JSON.parse(String(init?.body)) },
        },
      }),
    })
    const user = userEvent.setup()
    const line = await screen.findByLabelText(/^Linienfarbe/)
    // Palette mit Kontrast auf Weiß
    expect(line).toHaveTextContent('Zweitfarbe (#fbc707, Kontrast 1,6:1)')
    // Ersatzschrift erst bei einer Schrift der Webseite
    expect(screen.queryByLabelText(/^Ersatzschrift in Word \(Text\)/)).not.toBeInTheDocument()
    await user.selectOptions(line, '0')
    await user.selectOptions(screen.getByLabelText(/^Größe von Logo/), 'large')
    await user.click(screen.getByLabelText(/^Name als Text neben dem Logo/))
    await user.selectOptions(screen.getByLabelText(/^Schrift für den Text/), 'Source Sans 3')
    expect(await screen.findByLabelText(/^Ersatzschrift in Word \(Text\)/)).toBeInTheDocument()
    await waitFor(
      () => {
        const sent = calls
          .filter((c) => c.key === 'PATCH /api/orgs/7/letterhead/')
          .reduce((all, c) => ({ ...all, ...JSON.parse(String(c.init?.body)) }), {})
        expect(sent).toMatchObject({
          line_color: '0',
          logo_size: 'large',
          show_name: false,
          font: 'Source Sans 3',
        })
      },
      { timeout: 4000 },
    )
  })

  it('nimmt einen eigenen Namen im Briefkopf mit zwei Zeilen (Issue #487)', async () => {
    const calls = show('/einstellungen/briefbogen', {
      'GET /api/orgs/7/letterhead/': () => ({ status: 200, body: letterhead }),
      'GET /api/orgs/7/letterhead/preview/': () => ({ status: 200, body: '%PDF' }),
      'PATCH /api/orgs/7/letterhead/': (init) => ({
        status: 200,
        body: {
          ...letterhead,
          letterhead: { ...letterhead.letterhead, ...JSON.parse(String(init?.body)) },
        },
      }),
    })
    const user = userEvent.setup()
    const name = await screen.findByLabelText(/^Name im Briefkopf/)
    // „Zweite Zeile kleiner“ erst bei zwei Zeilen
    expect(screen.queryByLabelText(/^Zweite Zeile kleiner/)).not.toBeInTheDocument()
    await user.type(name, 'TV Beispielhausen{Enter}von 1900')
    await user.click(await screen.findByLabelText(/^Zweite Zeile kleiner/))
    await waitFor(
      () => {
        const sent = calls
          .filter((c) => c.key === 'PATCH /api/orgs/7/letterhead/')
          .reduce((all, c) => ({ ...all, ...JSON.parse(String(c.init?.body)) }), {})
        expect(sent).toMatchObject({
          head_name: 'TV Beispielhausen\nvon 1900',
          head_name_small: true,
        })
      },
      { timeout: 4000 },
    )
  })

  it('zeigt ein eigenes Logo für den Briefbogen (Issue #488)', async () => {
    show('/einstellungen/briefbogen', {
      'GET /api/orgs/7/letterhead/': () => ({
        status: 200,
        body: { ...letterhead, logo_url: '/media/logos/briefbogen/7-x.png' },
      }),
      'GET /api/orgs/7/letterhead/preview/': () => ({ status: 200, body: '%PDF' }),
    })
    expect(
      await screen.findByRole('heading', { name: 'Logo für den Briefbogen' }),
    ).toBeInTheDocument()
    expect(
      screen
        .getAllByAltText('Logo')
        .some((img) => img.getAttribute('src') === '/media/logos/briefbogen/7-x.png'),
    ).toBe(true)
    expect(screen.getByText('Anderes Bild wählen')).toBeInTheDocument()
  })
})
