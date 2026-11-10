import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedOut = () => ({ status: 401, body: { status: 401, data: { flows: [] } } })

function renderAt(path: string) {
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

function page(mine: null | { status: 'yes' | 'no' | 'maybe'; guests: number; note: string }) {
  return {
    club: 'TV Beispielhausen',
    owner: 'Jägerzug',
    imprint_key: 'k1',
    first_name: 'Anna',
    event: {
      title: 'Sommerfest',
      starts_at: '2099-06-13T12:00:00Z',
      ends_at: '2099-06-13T16:00:00Z',
      all_day: false,
      when: '13.06.2099, 14:00 bis 18:00 Uhr',
      location: 'Festplatz',
      address: 'Wiesenweg 1',
      description: 'Mit Grillen.',
      is_cancelled: false,
      cancel_note: '',
    },
    attachments: [
      { id: 3, name: 'Plan.pdf', size: 2048, url: '/api/public/rsvp/abc/attachments/3/' },
    ],
    rsvp: {
      deadline: '2099-06-10T16:00:00Z',
      capacity: null,
      free: null,
      guests_allowed: true,
      max_guests: 10,
      maybe_allowed: true,
      note_allowed: true,
      note_question: 'Essenswunsch?',
      can_respond: true,
      reason: '',
      mine,
    },
  }
}

describe('Rückmeldung per Link', () => {
  it('zeigt Termin und Anhänge und speichert erst nach Klick', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/rsvp/abc/': () => ({ status: 200, body: page(null) }),
      'POST /api/public/rsvp/abc/': () => ({
        status: 200,
        body: page({ status: 'maybe', guests: 0, note: 'Vegetarisch' }),
      }),
    })
    renderAt('/rueckmeldung/abc')
    expect(await screen.findByRole('heading', { name: 'Sommerfest' })).toBeInTheDocument()
    expect(screen.getByText('Festplatz, Wiesenweg 1')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Plan.pdf' })).toHaveAttribute(
      'href',
      '/api/public/rsvp/abc/attachments/3/',
    )
    expect(screen.getByText(/noch nicht zurückgemeldet/)).toBeInTheDocument()
    expect(calls.some((c) => c.key.startsWith('POST'))).toBe(false)
    fireEvent.click(screen.getByRole('radio', { name: 'Vielleicht' }))
    fireEvent.change(screen.getByLabelText('Essenswunsch?'), { target: { value: 'Vegetarisch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(await screen.findByText(/deine Rückmeldung: Vielleicht/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/public/rsvp/abc/')!
    expect(JSON.parse(String(post.init?.body))).toEqual({
      status: 'maybe',
      guests: 0,
      note: 'Vegetarisch',
    })
  })

  it('meldet ungültige Links', async () => {
    fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/rsvp/alt/': () => ({ status: 404, body: { detail: 'Nicht gefunden.' } }),
    })
    renderAt('/rueckmeldung/alt')
    expect(await screen.findByText('Dieser Link ist ungültig oder abgelaufen.')).toBeInTheDocument()
  })

  it('zeigt nach dem Anmeldeschluss nur den Stand', async () => {
    const body = page({ status: 'yes', guests: 2, note: '' })
    body.rsvp.can_respond = false
    body.rsvp.reason = 'Der Anmeldeschluss ist vorbei.'
    fakeApi({
      [SESSION]: loggedOut,
      'GET /api/public/rsvp/abc/': () => ({ status: 200, body }),
    })
    renderAt('/rueckmeldung/abc')
    expect(await screen.findByText('Der Anmeldeschluss ist vorbei.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Speichern' })).toBeNull())
    expect(screen.getByText(/Mit 2 Begleitpersonen/)).toBeInTheDocument()
  })
})
