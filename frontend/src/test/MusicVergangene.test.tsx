import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { MusicPage } from '../pages/music/MusicPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, modules: ['music'], permissions: ['music.view'] }),
}))

const base = 'GET /api/orgs/7/music/'

it('blendet vergangene Auftritte zunächst aus und auf Wunsch ein', async () => {
  fakeApi(
    Object.fromEntries(
      Object.entries({
        musicians: [],
        skills: [],
        performances: [
          {
            id: 1,
            title: 'Musterkonzert 2019',
            starts_at: '2019-10-04T18:00:00Z',
            ends_at: '2019-10-04T20:00:00Z',
          },
          {
            id: 2,
            title: 'Musterumzug 2099',
            starts_at: '2099-06-01T10:00:00Z',
            ends_at: '2099-06-01T12:00:00Z',
          },
        ],
        positions: [],
        assignments: [],
        'musicians/choices': { events: [], partners: [] },
        uniforms: [],
        'performance-kinds': [],
      }).map(([key, body]) => [`${base}${key}/`, () => ({ status: 200, body })]),
    ),
  )
  render(
    <MemoryRouter>
      <MusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText('Musterumzug 2099')).toBeInTheDocument()
  expect(screen.queryByText('Musterkonzert 2019')).not.toBeInTheDocument()
  const box = screen.getByRole('checkbox', { name: /Vergangene Auftritte zeigen/ })
  expect(box).not.toBeChecked()
  expect(screen.getByText(/1 ausgeblendet/)).toBeInTheDocument()
  await userEvent.click(box)
  expect(screen.getByText('Musterkonzert 2019')).toBeInTheDocument()
})
