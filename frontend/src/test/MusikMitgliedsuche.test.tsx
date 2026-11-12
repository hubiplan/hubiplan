import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { MusicPage } from '../pages/music/MusicPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({
    id: 7,
    modules: ['music'],
    permissions: ['music.view', 'music.edit', 'members.view'],
  }),
}))

const BASE = 'GET /api/orgs/7/music/'
const lists = (extra: Record<string, unknown> = {}) =>
  Object.fromEntries(
    Object.entries({
      musicians: [{ id: 1, membership: 5, display_name: 'Alex Beispiel', active: true }],
      skills: [],
      performances: [],
      positions: [],
      assignments: [],
      // Gesamtaudit 11.11., P-04: die Auswahl liefert keine Mitgliederliste mehr
      'musicians/choices': { events: [], partners: [] },
      ...extra,
    }).map(([key, body]) => [`${BASE}${key}/`, () => ({ status: 200, body })]),
  )

it('wählt das Mitglied eines neuen Musikers per Suche statt aus einer Gesamtliste', async () => {
  const calls = fakeApi({
    ...lists(),
    'GET /api/orgs/7/members/?suche=Mus&status=aktiv&page_size=8': () => ({
      status: 200,
      body: { count: 1, results: [{ id: 9, last_name: 'Muster', first_name: 'Anna' }] },
    }),
    'POST /api/orgs/7/music/musicians/': () => ({ status: 201, body: { id: 2 } }),
  })
  render(
    <MemoryRouter initialEntries={['/musik/musiker']}>
      <MusicPage />
    </MemoryRouter>,
  )
  await userEvent.click(await screen.findByRole('button', { name: 'Neuer Musiker' }))
  await userEvent.type(screen.getByRole('searchbox', { name: 'Mitglied' }), 'Mus')
  await userEvent.click(await screen.findByRole('button', { name: /Muster, Anna/ }))
  expect(screen.getByText(/Muster, Anna/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  const post = calls.find((c) => c.key === 'POST /api/orgs/7/music/musicians/')
  expect(JSON.parse(String(post?.init?.body)).membership).toBe('9')
})

it('belegt das Mitglied aus der Mitgliedsakte vor und lädt nur dessen Namen', async () => {
  const calls = fakeApi({
    ...lists(),
    'GET /api/orgs/7/members/5/': () => ({
      status: 200,
      body: { id: 5, last_name: 'Beispiel', first_name: 'Alex' },
    }),
  })
  render(
    <MemoryRouter initialEntries={['/musik/musiker?mitglied=5&id=neu']}>
      <MusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText(/Beispiel, Alex/)).toBeInTheDocument()
  expect(calls.some((c) => c.key.includes('/members/?'))).toBe(false)
})
