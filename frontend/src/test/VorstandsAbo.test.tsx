import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { FeedPanel } from '../components/calendar/Rsvp.tsx'
import { fakeApi } from './fakeApi.ts'

const base = '/api/portal/5/'
const off = { active: false, ics_url: null }

describe('Vorstands-Abo unter Termine › Kalender-Abo', () => {
  it('zeigt Vorstandsmitgliedern einen eigenen Link nur mit Vorstandsterminen', async () => {
    const calls = fakeApi({
      [`GET ${base}events/feed/`]: () => ({ status: 200, body: off }),
      [`GET ${base}events/board-feed/`]: () => ({
        status: 200,
        body: { ...off, available: true },
      }),
      [`PUT ${base}events/board-feed/`]: () => ({
        status: 200,
        body: {
          available: true,
          active: true,
          ics_url: 'https://verein.example.org/api/public/feed/abc/vorstand.ics',
        },
      }),
    })
    render(<FeedPanel base={base} />)
    expect(await screen.findByRole('heading', { name: 'Vorstands-Abo' })).toBeInTheDocument()
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Link für den Vorstand erstellen' }))
    expect(await screen.findByText(/vorstand\.ics/)).toBeInTheDocument()
    expect(calls.some((c) => c.key === `PUT ${base}events/board-feed/`)).toBe(true)
    // Das persönliche Abo bleibt unberührt
    expect(calls.some((c) => c.key === `PUT ${base}events/feed/`)).toBe(false)
  })

  it('Mitglieder ohne Vorstandsrolle sehen kein Vorstands-Abo', async () => {
    fakeApi({
      [`GET ${base}events/feed/`]: () => ({ status: 200, body: off }),
      [`GET ${base}events/board-feed/`]: () => ({
        status: 200,
        body: { ...off, available: false },
      }),
    })
    render(<FeedPanel base={base} />)
    expect(
      await screen.findByRole('button', { name: 'Persönlichen Link erstellen' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Vorstands-Abo' })).not.toBeInTheDocument()
  })
})
