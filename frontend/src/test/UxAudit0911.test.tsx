// Web-Korrekturen aus dem UI/UX-Audit vom 08.11.2026, zweite Runde (W-07, W-10, W-11, X-01)
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, retry, statusMessage } from '../api/client.ts'
import { OfflineBanner } from '../components/OfflineBanner.tsx'
import { EmptyState, Loading } from '../components/ui.tsx'

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, get: () => value })
}

describe('W-10: ohne Netz sofort Bescheid geben', () => {
  afterEach(() => {
    setOnline(true)
    retry.delays = []
    vi.unstubAllGlobals()
  })

  it('zeigt das Band, sobald die Verbindung weg ist, und blendet es wieder aus', () => {
    render(<OfflineBanner />)
    expect(screen.queryByRole('status')).toBeNull()
    act(() => {
      setOnline(false)
      window.dispatchEvent(new Event('offline'))
    })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Keine Verbindung. Änderungen werden gespeichert, sobald die Verbindung wieder da ist.',
    )
    act(() => {
      setOnline(true)
      window.dispatchEvent(new Event('online'))
    })
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('wiederholt ohne Netz nicht, sondern meldet gleich „Keine Verbindung“', async () => {
    retry.delays = [0, 0, 0]
    setOnline(false)
    const fn = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fn)
    const err = await api.get('/api/x/').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(0)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('ändernde Anfragen warten höchstens etwa zehn Sekunden', async () => {
    // 1 + 2 + 3 + 4 s passen nicht mehr ins Budget: nach drei Pausen ist Schluss
    retry.delays = [1000, 2000, 3000, 4000, 5000]
    vi.useFakeTimers()
    document.cookie = 'csrftoken=t'
    const fn = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fn)
    const done = api.patch('/api/x/', { a: 1 }).catch((e: unknown) => e)
    await vi.runAllTimersAsync()
    const err = await done
    vi.useRealTimers()
    expect((err as ApiError).status).toBe(0)
    expect(fn).toHaveBeenCalledTimes(4)
  })

  it('Serverfehler ohne Fachwort und ohne Klammern', () => {
    expect(statusMessage(500)).toBe(
      'Der Server antwortet gerade nicht. Bitte später erneut versuchen.',
    )
  })
})

describe('W-11: einheitliche Lade- und Leerzustände', () => {
  it('Laden heißt überall „Wird geladen …“', () => {
    render(<Loading />)
    expect(screen.getByText('Wird geladen …')).toBeInTheDocument()
  })

  it('Leerzustand nennt, was hier entsteht, und den nächsten Schritt', () => {
    render(
      <EmptyState title="Noch keine Auftritte." action={<button>Neuer Auftritt</button>}>
        Lege einen Auftritt zu einem Termin an.
      </EmptyState>,
    )
    expect(screen.getByText('Noch keine Auftritte.')).toBeInTheDocument()
    expect(screen.getByText('Lege einen Auftritt zu einem Termin an.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Neuer Auftritt' })).toBeInTheDocument()
  })
})
