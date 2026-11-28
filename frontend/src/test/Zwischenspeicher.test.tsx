// Gemeinsamer Zwischenspeicher für Stammdaten (components/shared.ts): teilt Anfragen, vergisst
// nach Änderungen und beim Kontowechsel, zeigt nie Daten eines anderen Schlüssels.
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mutationListeners, nextAuthGeneration } from '../api/client.ts'
import { clearShared, SHARED_FRESH_MS, useShared } from '../components/shared.ts'

afterEach(() => {
  vi.useRealTimers()
  clearShared()
})

const changed = (status: number) => {
  for (const listener of mutationListeners) listener('/api/orgs/7/x/', status, new Headers())
}

describe('useShared', () => {
  it('lädt gleiche Daten nur einmal, auch für zwei Bausteine zugleich', async () => {
    const loader = vi.fn(async () => ['a'])
    const first = renderHook(() => useShared('liste:7', loader))
    const second = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(second.result.current.data).toEqual(['a']))
    expect(first.result.current.data).toEqual(['a'])
    expect(loader).toHaveBeenCalledTimes(1)
  })

  it('zeigt frische Daten beim nächsten Einbinden sofort und ohne Anfrage', async () => {
    const loader = vi.fn(async () => ['a'])
    const first = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(first.result.current.data).toEqual(['a']))
    first.unmount()
    const second = renderHook(() => useShared('liste:7', loader))
    expect(second.result.current.data).toEqual(['a'])
    expect(second.result.current.loading).toBe(false)
    expect(loader).toHaveBeenCalledTimes(1)
  })

  it('lädt nach Ablauf der Frist neu und zeigt bis dahin den alten Stand', async () => {
    let now = 1_000_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    const loader = vi.fn().mockResolvedValueOnce(['alt']).mockResolvedValueOnce(['neu'])
    const first = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(first.result.current.data).toEqual(['alt']))
    first.unmount()
    now += SHARED_FRESH_MS + 1
    const second = renderHook(() => useShared('liste:7', loader))
    expect(second.result.current.data).toEqual(['alt'])
    await waitFor(() => expect(second.result.current.data).toEqual(['neu']))
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('vergisst alles nach einer erfolgreichen Änderung, nicht nach einer abgelehnten', async () => {
    const loader = vi.fn().mockResolvedValueOnce(['alt']).mockResolvedValueOnce(['neu'])
    const first = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(first.result.current.data).toEqual(['alt']))
    first.unmount()
    changed(400)
    const still = renderHook(() => useShared('liste:7', loader))
    expect(still.result.current.data).toEqual(['alt'])
    still.unmount()
    changed(200)
    const second = renderHook(() => useShared('liste:7', loader))
    expect(second.result.current.data).toBeNull()
    await waitFor(() => expect(second.result.current.data).toEqual(['neu']))
  })

  it('zeigt nach Abmelden oder Kontowechsel nichts vom vorigen Konto', async () => {
    const loader = vi.fn().mockResolvedValueOnce(['Konto A']).mockResolvedValueOnce(['Konto B'])
    const first = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(first.result.current.data).toEqual(['Konto A']))
    first.unmount()
    nextAuthGeneration()
    const second = renderHook(() => useShared('liste:7', loader))
    expect(second.result.current.data).toBeNull()
    await waitFor(() => expect(second.result.current.data).toEqual(['Konto B']))
  })

  it('speichert keine Antwort, die erst nach dem Abmelden eintrifft', async () => {
    let answer: (value: string[]) => void = () => {}
    const loader = vi
      .fn()
      .mockImplementationOnce(() => new Promise<string[]>((resolve) => (answer = resolve)))
      .mockResolvedValueOnce(['Konto B'])
    const first = renderHook(() => useShared('liste:7', loader))
    nextAuthGeneration()
    clearShared()
    await act(async () => answer(['Konto A']))
    first.unmount()
    const second = renderHook(() => useShared('liste:7', loader))
    expect(second.result.current.data).toBeNull()
    await waitFor(() => expect(second.result.current.data).toEqual(['Konto B']))
  })

  it('zeigt beim Wechsel der Einheit nie die Daten der vorigen', async () => {
    const loader = vi.fn(async (org: number) => [`Einheit ${org}`])
    const hook = renderHook(({ org }) => useShared(`liste:${org}`, () => loader(org)), {
      initialProps: { org: 7 },
    })
    await waitFor(() => expect(hook.result.current.data).toEqual(['Einheit 7']))
    hook.rerender({ org: 8 })
    expect(hook.result.current.data).toBeNull()
    await waitFor(() => expect(hook.result.current.data).toEqual(['Einheit 8']))
  })

  it('reload lädt immer neu, setData gilt auch für den nächsten Baustein', async () => {
    const loader = vi.fn().mockResolvedValueOnce(['a']).mockResolvedValueOnce(['b'])
    const hook = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(hook.result.current.data).toEqual(['a']))
    await act(() => hook.result.current.reload())
    expect(hook.result.current.data).toEqual(['b'])
    act(() => hook.result.current.setData(['c']))
    const next = renderHook(() => useShared('liste:7', loader))
    expect(next.result.current.data).toEqual(['c'])
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('meldet Fehler wie useLoad und merkt sich nichts davon', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new TypeError('x')).mockResolvedValueOnce(['a'])
    const hook = renderHook(() => useShared('liste:7', loader))
    await waitFor(() => expect(hook.result.current.error).toBeTruthy())
    await act(() => hook.result.current.reload())
    expect(hook.result.current.error).toBeNull()
    expect(hook.result.current.data).toEqual(['a'])
  })
})
