import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { memberApi } from '../api/members.ts'
import type { MemberRow } from '../api/members.ts'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'
import { RecordPager } from '../components/liste/RecordPager.tsx'
import { rememberOrder } from '../components/liste/recordOrder.ts'

// Web-Oberfläche W11: Filterchips, gemerkte Ansichten und Seitenblatt in der Mitgliederliste
const SESSION = 'GET /_allauth/browser/v1/auth/session'
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

function setup() {
  fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [ORG] }),
    [`GET ${base}/member-types/`]: () => ({ status: 200, body: [{ id: 3, name: 'aktiv' }] }),
    [`GET ${base}/departments/`]: () => ({ status: 200, body: [] }),
    [`GET ${base}/honorary-titles/`]: () => ({ status: 200, body: [] }),
  })
  vi.spyOn(memberApi, 'list').mockResolvedValue({
    count: 1,
    results: [row],
    next: null,
    previous: null,
  })
  return render(
    <MemoryRouter initialEntries={['/mitglieder']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Tabellenbaustein in der Mitgliederliste', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('zeigt gesetzte Filter als Chips und entfernt sie mit einem Klick', async () => {
    const user = userEvent.setup()
    setup()
    await screen.findByText('Muster, Erika')
    expect(screen.queryByRole('group', { name: 'Gesetzte Filter' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Status'), 'ehemalig')
    await user.selectOptions(screen.getByLabelText('Mitgliedsart'), '3')
    const chips = await screen.findByRole('group', { name: 'Gesetzte Filter' })
    await user.click(
      within(chips).getByRole('button', { name: 'Filter entfernen: Mitgliedsart: aktiv' }),
    )
    expect(screen.getByLabelText('Mitgliedsart')).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Filter entfernen: ehemalige Mitglieder' }))
    expect(screen.getByLabelText('Status')).toHaveValue('aktiv')
  })

  it('merkt eine Ansicht unter einem Namen und stellt sie wieder her', async () => {
    const user = userEvent.setup()
    setup()
    await screen.findByText('Muster, Erika')
    await user.selectOptions(screen.getByLabelText('Status'), 'ehemalig')
    await user.click(screen.getByRole('button', { name: 'Als Ansicht merken' }))
    await user.type(screen.getByRole('textbox', { name: 'Name der Ansicht' }), 'Ehemalige')
    await user.click(screen.getByRole('button', { name: 'Merken' }))
    expect(screen.getByLabelText('Ansicht')).toHaveValue('Ehemalige')
    await user.selectOptions(screen.getByLabelText('Ansicht'), '')
    expect(screen.getByLabelText('Status')).toHaveValue('aktiv')
    await user.selectOptions(screen.getByLabelText('Ansicht'), 'Ehemalige')
    expect(screen.getByLabelText('Status')).toHaveValue('ehemalig')
    await user.click(screen.getByRole('button', { name: 'Ansicht löschen' }))
    // ohne gemerkte Ansicht keine Auswahl mehr, nur noch „Als Ansicht merken“
    expect(screen.queryByLabelText('Ansicht')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Als Ansicht merken' })).toBeVisible()
  })

  it('öffnet auf breiten Bildschirmen ein Seitenblatt mit Link zur Akte', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByText('Turnen'))
    const sheet = screen.getByRole('dialog', { name: 'Muster, Erika' })
    expect(within(sheet).getByRole('link', { name: 'erika@beispiel.test' })).toHaveAttribute(
      'href',
      'mailto:erika@beispiel.test',
    )
    expect(within(sheet).getByRole('link', { name: 'Akte öffnen' })).toHaveAttribute(
      'href',
      '/mitglieder/11',
    )
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('Blättern in der Akte', () => {
  it('führt zum vorherigen und nächsten Eintrag der zuletzt gezeigten Liste', () => {
    rememberOrder('mitglieder.7', [4, 11, 9])
    render(
      <MemoryRouter>
        <RecordPager
          list="mitglieder.7"
          current={11}
          path={(id) => `/mitglieder/${id}`}
          label={{ prev: 'Vorheriges Mitglied', next: 'Nächstes Mitglied' }}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: /Vorheriges Mitglied/ })).toHaveAttribute(
      'href',
      '/mitglieder/4',
    )
    expect(screen.getByRole('link', { name: /Nächstes Mitglied/ })).toHaveAttribute(
      'href',
      '/mitglieder/9',
    )
    expect(screen.getByText('2 von 3')).toBeInTheDocument()
  })

  it('fehlt, wenn der Eintrag nicht in der Liste steht', () => {
    rememberOrder('mitglieder.7', [4, 9])
    const { container } = render(
      <MemoryRouter>
        <RecordPager
          list="mitglieder.7"
          current={11}
          path={(id) => `/m/${id}`}
          label={{ prev: 'a', next: 'b' }}
        />
      </MemoryRouter>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
