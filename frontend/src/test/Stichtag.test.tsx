import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { censusApi } from '../api/statistics.ts'
import type { CensusStats } from '../api/statistics.ts'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

const row = (label: string, counts: number[]) => ({
  label,
  counts,
  total: counts.reduce((a, b) => a + b, 0),
})

// Erfundene Zahlen eines Mustervereins
const census: CensusStats = {
  stichtag: '2026-01-01',
  alter: 'sport',
  zaehlung: 'stichtag',
  schemes: [
    { key: 'sport', label: 'Sportbund' },
    { key: 'jugend', label: 'Jugendförderung' },
  ],
  age_groups: ['bis 6', 'über 60'],
  gender_labels: ['männlich', 'weiblich', 'divers', 'ohne Angabe'],
  types: [
    { id: 1, name: 'aktiv', count: 3 },
    { id: 2, name: 'passiv', count: 1 },
  ],
  arten: null,
  total: 5,
  persons: 4,
  organizations: 1,
  rows: [
    row('bis 6', [1, 1, 0, 0]),
    row('über 60', [0, 1, 0, 1]),
    row('ohne Geburtsdatum', [0, 0, 0, 0]),
  ],
  genders: [1, 2, 0, 1],
  places: [
    {
      city: 'Musterstadt',
      postal_codes: ['12345'],
      genders: [1, 2, 0, 0],
      ages: [2, 1, 0],
      total: 3,
      missing: false,
    },
  ],
  groups_title: 'Abteilung',
  groups: [
    {
      id: 9,
      name: 'Fußball',
      organizations: 0,
      rows: [row('bis 6', [1, 0, 0, 0]), row('über 60', [0, 0, 0, 0])],
      genders: [1, 0, 0, 0],
      total: 1,
    },
  ],
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

describe('Stichtagsstatistik', () => {
  it('zeigt Alter × Geschlecht, Wohnorte, Abteilungen und Dateien', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ modules: ['members'], permissions: ['members.view'] })],
      }),
    })
    const load = vi.spyOn(censusApi, 'load').mockResolvedValue(census)
    renderApp('/mitglieder/entwicklung/stichtag')
    const ages = await screen.findByRole('table', { name: 'Alter und Geschlecht' })
    expect(within(ages).getByRole('row', { name: /über 60/ })).toHaveTextContent('2')
    // Leere Zeile „ohne Geburtsdatum“ bleibt weg
    expect(within(ages).queryByText('ohne Geburtsdatum')).not.toBeInTheDocument()
    expect(screen.getByText('Musterstadt')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Abteilung: Fußball' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CSV' })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/orgs/7/members/statistics/stichtag/?'),
    )
    expect(load).toHaveBeenLastCalledWith(
      '/api/orgs/7/members/statistics/stichtag/',
      expect.objectContaining({ alter: 'sport', zaehlung: 'stichtag' }),
    )
    await userEvent.selectOptions(screen.getByLabelText('Altersgruppen'), 'jugend')
    expect(load).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.objectContaining({ alter: 'jugend' }),
    )
    await userEvent.click(screen.getByRole('checkbox', { name: /passiv/ }))
    expect(load).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.objectContaining({ arten: [1] }),
    )
  })
})
