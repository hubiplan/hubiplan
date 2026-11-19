// UX-Audit 16.11.2026, VW-38: ohne Verbindung nur eine Meldung (das Band), danach von selbst neu laden.
import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OfflineBanner } from '../components/OfflineBanner.tsx'
import { LoadError } from '../components/ui.tsx'
import { showNotice, useUndo } from '../components/undo.ts'

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, get: () => value })
}

describe('VW-38: eine Meldung ohne Verbindung', () => {
  afterEach(() => setOnline(true))

  it('zeigt offline nur das Band und lädt bei Rückkehr der Verbindung neu', () => {
    const retry = vi.fn()
    setOnline(false)
    render(
      <>
        <OfflineBanner />
        <LoadError message="Die Termine konnten nicht geladen werden." onRetry={retry} />
      </>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Keine Verbindung.')
    expect(screen.queryByRole('alert')).toBeNull()
    act(() => {
      setOnline(true)
      window.dispatchEvent(new Event('online'))
    })
    expect(retry).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent('Die Termine konnten nicht geladen werden.')
  })
})

describe('VW-29: Meldung nach Löschen ohne Rückgängig am selben Ort', () => {
  it('zeigt „Entwurf gelöscht.“ ohne Rückgängig-Knopf', () => {
    function Probe() {
      const { notice } = useUndo('/api/orgs/7')
      return <p>{notice ? `${notice.text}|${notice.action ?? 'ohne'}` : 'leer'}</p>
    }
    render(<Probe />)
    act(() => showNotice('/api/orgs/7/circulars/3/', 'Entwurf gelöscht.'))
    expect(screen.getByText('Entwurf gelöscht.|ohne')).toBeInTheDocument()
  })
})
