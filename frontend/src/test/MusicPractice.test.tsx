import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import { OwnPracticePanel } from '../pages/music/OwnPractice.tsx'
import { fakeApi } from './fakeApi.ts'

it('beantwortet eine einzelne Probe und zeigt persönliche Noten und Rückgaben', async () => {
  const url = '/api/portal/9/music/practice/'
  const calls = fakeApi({
    ['GET ' + url]: () => ({
      status: 200,
      body: {
        rehearsals: [
          {
            id: 3,
            title: 'Musterprobe',
            starts_at: '2026-12-01T18:00:00Z',
            original_start: '2026-12-01T18:00:00Z',
            status: 'pending',
            can_respond: true,
            items: [{ title: 'Musterlied', focus: 'Takte 1 bis 8' }],
          },
        ],
        scores: [
          {
            id: 4,
            piece: 'Musterlied',
            title: 'Tuba 1',
            url: '/api/portal/9/music/files/4/',
            usage_note: 'Vereinsnutzung',
          },
        ],
        loans: [
          {
            id: 5,
            title: 'Musterlied',
            quantity: 2,
            returned: 1,
            due_on: '2026-12-10',
            overdue: false,
          },
        ],
      },
    }),
    ['POST ' + url]: () => ({ status: 200, body: { ok: true } }),
  })
  render(
    <MemoryRouter>
      <OwnPracticePanel accessId={9} />
    </MemoryRouter>,
  )
  await screen.findByText('Takte 1 bis 8', { exact: false })
  expect(screen.getByRole('link', { name: 'Musterlied · Tuba 1' })).toHaveAttribute(
    'href',
    '/api/portal/9/music/files/4/',
  )
  expect(screen.getByText(/Noch zurückzugeben/)).toHaveTextContent('1')
  await userEvent.click(screen.getByRole('button', { name: 'Zusagen' }))
  expect(JSON.parse(String(calls.find((c) => c.key === 'POST ' + url)?.init?.body))).toMatchObject({
    id: 3,
    original_start: '2026-12-01T18:00:00Z',
    status: 'accepted',
  })
})
