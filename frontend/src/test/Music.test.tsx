import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { MusicPage } from '../pages/music/MusicPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, modules: ['music'], permissions: ['music.view'] }),
}))

it('zählt bestätigte Musiker und offene Besetzungsplätze auch mit Absagen richtig', async () => {
  const base = 'GET /api/orgs/7/music/'
  fakeApi(
    Object.fromEntries(
      Object.entries({
        musicians: [{ id: 1, display_name: 'Alex Beispiel' }],
        skills: [],
        performances: [{ id: 1, title: 'Musterkonzert' }],
        positions: [{ id: 2, performance: 1, instrument: 'Tuba', required: 3 }],
        assignments: [
          { id: 1, performance: 1, position: 2, musician: 1, status: 'accepted' },
          { id: 2, performance: 1, position: 2, musician: 2, status: 'declined' },
        ],
        'musicians/choices': { events: [], members: [], partners: [] },
      }).map(([key, body]) => [`${base}${key}/`, () => ({ status: 200, body })]),
    ),
  )
  render(
    <MemoryRouter>
      <MusicPage />
    </MemoryRouter>,
  )
  await screen.findByText('Musterkonzert')
  await userEvent.click(screen.getByRole('button', { name: 'Sollbesetzung' }))
  expect(await screen.findByText(/Zugesagt.*1.*Fehlend.*2/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Anlegen' })).not.toBeInTheDocument()
  await userEvent.type(screen.getByRole('searchbox', { name: 'Einträge suchen' }), 'Posaune')
  expect(screen.getByText('Keine passenden Einträge gefunden.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('link', { name: 'Musiker' }))
  expect(await screen.findByText('Alex Beispiel')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Musiker' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('button', { name: 'Instrumentale Fähigkeiten' })).toBeInTheDocument()
  expect(screen.getByRole('searchbox', { name: 'Einträge suchen' })).toHaveValue('')
})
