// Zuwendungsbestätigungen: nur bei eingetragenen Vereinen, Sammelbestätigung ausstellen.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { financeAccess, financeSections } from '../pages/finanzen/access.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'
const YEAR = new Date().getFullYear()

const base = {
  modules: ['members', 'finance', 'donations'],
  permissions: ['finance.view', 'finance.edit'],
}

const SETTINGS = {
  purposes: 'des Brauchtums',
  notice: 'exemption',
  notice_label: 'Freistellungsbescheid',
  tax_office: 'Neuss',
  tax_number: '122/5701/0000',
  notice_date: '2025-03-01',
  assessment_period: '2021 bis 2023',
  fees_allowed: false,
  place: 'Neuss',
  valid_until: '2030-03-01',
  problems: [],
}

function donation(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    date: `${YEAR}-01-1${id}`,
    kind: 'money',
    kind_label: 'Geldzuwendung',
    amount: '100.00',
    waiver: false,
    membership: null,
    donor_name: 'Max Muster',
    donor_address: '',
    goods_description: '',
    goods_origin: '',
    goods_documents: false,
    note: '',
    booking: null,
    booking_number: null,
    statement: null,
    statement_number: null,
    ...extra,
  }
}

function renderApp(path: string) {
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

describe('Zuwendungsbestätigungen', () => {
  it('erscheinen mit Modul und Kasse, auch ohne Registereintrag', () => {
    const plain = financeSections(
      financeAccess(testOrg({ ...base, registered: false }) as unknown as OrgSummary),
    )
    expect(plain.map((s) => s.label)).toContain('Zuwendungsbestätigungen')
    const noFinance = financeSections(
      financeAccess(testOrg({ ...base, modules: ['members'] }) as unknown as OrgSummary),
    )
    expect(noFinance.map((s) => s.label)).not.toContain('Zuwendungsbestätigungen')
    const noModule = financeSections(
      financeAccess(testOrg({ ...base, modules: ['members', 'finance'] }) as unknown as OrgSummary),
    )
    expect(noModule.map((s) => s.label)).not.toContain('Zuwendungsbestätigungen')
  })

  it('zwei Zuwendungen ankreuzen ergibt eine Sammelbestätigung', async () => {
    let issued: unknown = null
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ ...base, registered: true })],
      }),
      [`GET ${F}/donation-settings/`]: () => ({ status: 200, body: SETTINGS }),
      [`GET ${F}/donations/?jahr=${YEAR}`]: () => ({
        status: 200,
        body: { count: 2, next: null, previous: null, results: [donation(1), donation(2)] },
      }),
      [`POST ${F}/donation-statements/`]: (init) => {
        issued = JSON.parse(String(init?.body))
        return { status: 201, body: { id: 9, number: `ZB-${YEAR}-0001`, donor_name: 'Max Muster' } }
      },
    })
    const user = userEvent.setup()
    renderApp('/finanzen/zuwendungen')
    const boxes = await screen.findAllByRole('checkbox', { name: /Max Muster .* auswählen/ })
    await user.click(boxes[0])
    await user.click(boxes[1])
    await user.click(screen.getByRole('button', { name: 'Sammelbestätigung ausstellen' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Unterschrift durch (Name)'), 'Erika Kasse')
    await user.click(within(dialog).getByRole('button', { name: 'Ausstellen' }))
    await waitFor(() => expect(issued).toEqual({ donations: [1, 2], signer_name: 'Erika Kasse' }))
    expect(await screen.findByText(/ZB-\d{4}-0001 für Max Muster ausgestellt/)).toBeInTheDocument()
  })

  it('bietet den vereinfachten Nachweis bis 300 € als PDF und Text', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg(base)] }),
      [`GET ${F}/donation-settings/`]: () => ({
        status: 200,
        body: { enabled: true, ...SETTINGS },
      }),
      [`GET ${F}/donation-settings/simplified/`]: () => ({
        status: 200,
        body: { text: 'Vereinfachter Zuwendungsnachweis für Zuwendungen bis 300 €\n\nMuster' },
      }),
    })
    renderApp('/finanzen/einrichtung/zuwendungen')
    const card = await screen.findByTestId('simplified-proof')
    expect(within(card).getByRole('link', { name: 'Beleg als PDF' })).toHaveAttribute(
      'href',
      `${F}/donation-settings/simplified/?als=pdf`,
    )
    await userEvent
      .setup()
      .click(within(card).getByRole('button', { name: 'Text für die Webseite' }))
    expect(await within(card).findByDisplayValue(/Zuwendungen bis 300 €/)).toBeInTheDocument()
  })

  it('zeigt zweckgebundene Spenden mit Rest und legt einen Zweck an', async () => {
    let created = false
    const earmark = (id: number, name: string, extra: Record<string, unknown> = {}) => ({
      id,
      name,
      note: '',
      is_active: true,
      received: '800.00',
      used: '200.00',
      rest: '600.00',
      first_donation: '2022-03-01',
      last_donation: '2022-03-01',
      overdue: true,
      ...extra,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg(base)] }),
      [`GET ${F}/earmarks/`]: () => ({
        status: 200,
        body: [
          earmark(1, 'Neue Fahne'),
          ...(created
            ? [
                earmark(2, 'Jugendzeltlager', {
                  received: '0.00',
                  used: '0.00',
                  rest: '0.00',
                  overdue: false,
                }),
              ]
            : []),
        ],
      }),
      [`POST ${F}/earmarks/`]: () => {
        created = true
        return { status: 201, body: { id: 2, name: 'Jugendzeltlager', note: '', is_active: true } }
      },
    })
    renderApp('/finanzen/zuwendungen/zweckbindungen')
    const card = await screen.findByTestId('earmarks')
    expect(within(card).getByText('Neue Fahne')).toBeInTheDocument()
    expect(within(card).getByText(/600,00/)).toBeInTheDocument()
    expect(within(card).getByText('zeitnah verwenden')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.type(within(card).getByLabelText('Zweck'), 'Jugendzeltlager')
    await user.click(within(card).getByRole('button', { name: 'Anlegen' }))
    expect(await within(card).findByText('Jugendzeltlager')).toBeInTheDocument()
  })
})
