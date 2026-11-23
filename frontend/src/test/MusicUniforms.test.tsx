import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { MusicPage } from '../pages/music/MusicPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, modules: ['music'], permissions: ['music.view'] }),
}))

const base = 'GET /api/orgs/7/music/'
const kinds = [
  { id: 1, name: 'Umzug', formation: 'march', uniform: 3, on_website: false, active: true },
  { id: 2, name: 'Konzert', formation: 'seated', uniform: null, on_website: true, active: true },
]
const uniforms = [
  {
    id: 3,
    name: 'Sommeruniform',
    description: 'Kurzarmhemd',
    checklist: ['Mütze', 'weiße Handschuhe'],
    has_image: false,
    active: true,
  },
]

function mock() {
  fakeApi(
    Object.fromEntries(
      Object.entries({
        musicians: [],
        skills: [],
        performances: [
          {
            id: 1,
            title: 'Musterfest Tag 1',
            starts_at: '2027-06-01T10:00:00Z',
            kind: 1,
            kind_name: 'Umzug',
            uniform_text: 'Sommeruniform · ohne Jacke',
            days: [2],
            main: null,
          },
          {
            id: 2,
            title: 'Musterfest Tag 2',
            starts_at: '2027-06-02T10:00:00Z',
            kind: 2,
            kind_name: 'Konzert',
            uniform_text: '',
            days: [],
            main: 1,
          },
        ],
        positions: [],
        assignments: [],
        'musicians/choices': { events: [], partners: [] },
        uniforms,
        'performance-kinds': kinds,
      }).map(([key, body]) => [`${base}${key}/`, () => ({ status: 200, body })]),
    ),
  )
}

it('zeigt Art, Uniform und Tage eines Festes, filtert und zählt nach Art', async () => {
  mock()
  render(
    <MemoryRouter>
      <MusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText('Sommeruniform · ohne Jacke')).toBeInTheDocument()
  expect(screen.getByText('für 2 Tage')).toBeInTheDocument()
  expect(screen.getByText('über Musterfest Tag 1')).toBeInTheDocument()
  await userEvent.click(screen.getByText('Auftritte je Jahr und Art'))
  const table = screen.getByRole('table')
  expect(within(table).getByRole('columnheader', { name: '2027' })).toBeInTheDocument()
  expect(within(table).getByRole('rowheader', { name: 'Konzert' })).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Auftrittsart' }), '2')
  expect(screen.queryByText('Musterfest Tag 1')).not.toBeInTheDocument()
  expect(screen.getAllByText('Musterfest Tag 2').length).toBeGreaterThan(0)
})

it('listet Uniformen mit Checkliste und Auftrittsarten mit Vorschlag', async () => {
  mock()
  render(
    <MemoryRouter initialEntries={['/musik/uniformen']}>
      <MusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText('weiße Handschuhe')).toBeInTheDocument()
  expect(screen.getByText(/Spielform: Umzug · Uniform: Sommeruniform/)).toBeInTheDocument()
  expect(screen.getByText(/Auf der Webseite genannt/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Uniform anlegen' })).not.toBeInTheDocument()
})
