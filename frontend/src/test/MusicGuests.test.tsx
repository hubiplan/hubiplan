import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { GuestMusicPage } from '../pages/music/GuestMusicPage.tsx'
import { GuestAccessPanel } from '../pages/music/GuestAccessPanel.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({ useActiveOrg: () => ({ id: 7 }) }))

const token = 'a'.repeat(64)
const row = {
  title: 'Musterkonzert',
  organization: 'Musterverein',
  status: 'pending',
  can_respond: true,
  starts_at: '2026-12-01T18:00:00Z',
  ends_at: '2026-12-01T20:00:00Z',
  location: 'Musterhalle',
  instrument: 'Tuba',
  register: '',
  uniform: 'Vereinshemd',
  program: [{ title: 'Musterstück', kind: 'piece' }],
  formation: 'standing',
  availability: [],
}

it('uses the fragment credential only as a bearer header without member cookies', async () => {
  let status = 'pending'
  const calls = fakeApi({
    'GET /api/music/guest/': () => ({ status: 200, body: { ...row, status } }),
    'POST /api/music/guest/': () => {
      status = 'accepted'
      return { status: 200, body: { status } }
    },
  })
  render(
    <MemoryRouter initialEntries={[`/musik-gast#${token}`]}>
      <GuestMusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByText('Musterstück')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Zusagen' }))
  await screen.findByText('Rückmeldung gespeichert.')
  const post = calls.find((c) => c.key.startsWith('POST'))!
  expect(post.key).toBe('POST /api/music/guest/')
  expect(post.init?.credentials).toBe('omit')
  expect(new Headers(post.init?.headers).get('Authorization')).toBe(`Bearer ${token}`)
  expect(JSON.parse(String(post.init?.body))).toEqual({ status: 'accepted' })
  expect(screen.getByRole('button', { name: 'Zusagen' })).toHaveAttribute('aria-pressed', 'true')
})

it('allows declining despite a conflict and hides revoked invitations', async () => {
  const calls = fakeApi({
    'GET /api/music/guest/': () => ({ status: 200, body: { ...row, availability: ['absence'] } }),
    'POST /api/music/guest/': () => ({ status: 404, body: {} }),
  })
  render(
    <MemoryRouter initialEntries={[`/musik-gast#${token}`]}>
      <GuestMusicPage />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('button', { name: 'Zusagen' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Absagen' }))
  await screen.findByText('Diese Einladung ist ungültig oder abgelaufen.')
  expect(JSON.parse(String(calls.find((c) => c.key.startsWith('POST'))?.init?.body))).toEqual({
    status: 'declined',
  })
})

it('rejects missing fragment credentials before requesting private information', () => {
  const calls = fakeApi({})
  render(
    <MemoryRouter initialEntries={['/musik-gast']}>
      <GuestMusicPage />
    </MemoryRouter>,
  )
  expect(screen.getByText('Diese Einladung ist ungültig oder abgelaufen.')).toBeInTheDocument()
  expect(calls).toEqual([])
})

it('creates a guest link and explicitly sends the invitation with retry protection', async () => {
  const url = '/api/orgs/7/music/assignments/9/guest-access/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({ status: 200, body: { active: false, has_email: true } }),
    [`POST ${url}`]: () => ({
      status: 200,
      body: {
        active: true,
        has_email: true,
        sent: true,
        auto_notify: true,
        url: `https://example.org/musik-gast#${token}`,
      },
    }),
  })
  render(<GuestAccessPanel assignment={9} name="Muster Gast" onClose={() => {}} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Einladungslink erstellen' }))
  expect(await screen.findByLabelText('Persönlicher Einladungslink')).toHaveValue(
    `https://example.org/musik-gast#${token}`,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Gasteinladung senden' }))
  await screen.findByText('Die Gasteinladung wurde an die Ausgangspost übergeben.')
  await waitFor(() => expect(calls.filter((c) => c.key.startsWith('POST'))).toHaveLength(2))
  for (const call of calls.filter((c) => c.key.startsWith('POST'))) {
    expect(new Headers(call.init?.headers).get('Idempotency-Key')).toBeTruthy()
  }
})
