import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client.ts'
import { useQueryLoad } from '../components/forms.ts'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((ok, fail) => {
    resolve = ok
    reject = fail
  })
  return { promise, resolve, reject }
}

describe('Ergebnisse der aktuellen Auswahl', () => {
  it('entfernt alte Ergebnisse sofort und ignoriert verspätete Antworten und Fehler', async () => {
    const requests = [
      deferred<string>(),
      deferred<string>(),
      deferred<string>(),
      deferred<string>(),
    ]
    const load = vi.fn((query: number) => requests[query].promise)
    const hook = renderHook(({ query }) => useQueryLoad(() => load(query), [query]), {
      initialProps: { query: 0 },
    })
    await act(async () => requests[0].resolve('Erste Auswahl'))
    expect(hook.result.current.data).toBe('Erste Auswahl')
    hook.rerender({ query: 1 })
    expect(hook.result.current.data).toBeNull()
    expect(hook.result.current.loading).toBe(true)
    hook.rerender({ query: 2 })
    await act(async () => requests[2].resolve('Aktuelle Auswahl'))
    await act(async () => requests[1].resolve('Überholte Auswahl'))
    expect(hook.result.current.data).toBe('Aktuelle Auswahl')
    hook.rerender({ query: 3 })
    hook.rerender({ query: 2 })
    await act(async () => requests[3].reject(new ApiError(500, { detail: 'Alter Fehler' })))
    expect(hook.result.current.data).toBe('Aktuelle Auswahl')
    expect(hook.result.current.error).toBeNull()
  })

  it('zeigt nach einem Fehler keine alten Zahlen und ermöglicht einen erneuten Versuch', async () => {
    const retry = deferred<string>()
    const load = vi
      .fn()
      .mockResolvedValueOnce('Alter Stand')
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Vorübergehend nicht verfügbar' }))
      .mockReturnValueOnce(retry.promise)
    const hook = renderHook(({ query }) => useQueryLoad(load, [query]), {
      initialProps: { query: 0 },
    })
    await waitFor(() => expect(hook.result.current.data).toBe('Alter Stand'))
    hook.rerender({ query: 1 })
    await waitFor(() => expect(hook.result.current.error).toBe('Vorübergehend nicht verfügbar'))
    expect(hook.result.current.data).toBeNull()
    let pending!: Promise<void>
    act(() => {
      pending = hook.result.current.reload()
    })
    expect(hook.result.current.error).toBeNull()
    expect(hook.result.current.loading).toBe(true)
    await act(async () => {
      retry.resolve('Neuer Stand')
      await pending
    })
    expect(hook.result.current.data).toBe('Neuer Stand')
  })

  it('fragt ohne erforderlichen Kontext nichts ab und verwirft Antworten nach dem Deaktivieren', async () => {
    const response = deferred<string>()
    const load = vi.fn(() => response.promise)
    const hook = renderHook(({ enabled }) => useQueryLoad(load, ['einheit'], enabled), {
      initialProps: { enabled: false },
    })
    expect(load).not.toHaveBeenCalled()
    hook.rerender({ enabled: true })
    expect(load).toHaveBeenCalledTimes(1)
    hook.rerender({ enabled: false })
    await act(async () => response.resolve('Nicht mehr benötigt'))
    expect(hook.result.current.data).toBeNull()
    hook.unmount()
  })
})
