import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { ProgramPanel } from '../pages/music/ProgramPanel.tsx'
import { ScoresPage } from '../pages/music/ScoresPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, permissions: ['music.view'], modules: ['music', 'events'] }),
}))

it('zeigt Programmdauer, fehlende Stimmen und lesende Exportmöglichkeiten', async () => {
  const base = 'GET /api/orgs/7/music/'
  fakeApi({
    [base + 'performances/3/']: () => ({ status: 200, body: { title: 'Musterkonzert', event: 8 } }),
    [base + 'arrangements/']: () => ({ status: 200, body: [] }),
    [base + 'performances/3/program/']: () => ({
      status: 200,
      body: {
        entries: [],
        total_seconds: 330,
        regular_seconds: 240,
        encore_seconds: 90,
        preparation: [
          {
            arrangement: 1,
            name: 'Musterfassung',
            title: 'Musterlied',
            paper_format: 'concert',
            active: true,
            missing_specification: false,
            license_note: 'Nur Vereinsnutzung',
            voices: [
              {
                instrument: 'Tuba',
                register: '1',
                kind: 'part',
                required: 2,
                planned: 2,
                accepted: 1,
                missing_players: 1,
                needed_copies: 2,
                copies: 0,
                missing_copies: 2,
                locations: ['Schrank A'],
              },
            ],
          },
        ],
      },
    }),
  })
  render(
    <MemoryRouter>
      <ProgramPanel performance={3} />
    </MemoryRouter>,
  )
  expect((await screen.findByText('Programmdauer')).nextElementSibling).toHaveTextContent('4:00')
  expect(screen.getByText('Nur Vereinsnutzung')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Stimmenliste herunterladen' })).toHaveAttribute(
    'href',
    '/api/orgs/7/music/performances/3/program/?export=parts',
  )
  expect(screen.getByRole('link', { name: 'Aufgaben für Notenvorbereitung' })).toHaveAttribute(
    'href',
    '/aufgaben?termin=8',
  )
  expect(screen.queryByRole('button', { name: 'Programmpunkt hinzufügen' })).not.toBeInTheDocument()
})

it('zeigt Noten ohne Dokumentenrecht ohne digitale Unterlagen anzufordern', async () => {
  const base = 'GET /api/orgs/7/music/'
  const calls = fakeApi(
    Object.fromEntries(
      Object.entries({
        pieces: [{ id: 1, title: 'Musterlied' }],
        arrangements: [
          { id: 2, piece: 1, name: 'Konzertfassung', duration_seconds: 180, active: true },
        ],
        parts: [],
        'score-documents': [],
      }).map(([key, body]) => [`${base}${key}/`, () => ({ status: 200, body })]),
    ),
  )
  render(
    <MemoryRouter>
      <ScoresPage />
    </MemoryRouter>,
  )
  await screen.findByText('Konzertfassung')
  expect(calls.some((c) => c.key.includes('/documents/'))).toBe(false)
  expect(screen.queryByRole('button', { name: 'Anlegen' })).not.toBeInTheDocument()
})
