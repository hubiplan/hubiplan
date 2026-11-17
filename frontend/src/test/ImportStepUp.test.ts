// Import mit frischer Bestätigung (Gesamtaudit 15.11., AZ-11): Nach der Bestätigung geht die
// Datei noch einmal vollständig hinaus.
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setStepUpHandler } from '../api/client.ts'
import { transferApi } from '../api/datatransfer.ts'

describe('Import mit frischer Bestätigung', () => {
  afterEach(() => {
    setStepUpHandler(null)
    vi.unstubAllGlobals()
  })

  it('sendet die Datei nach der Bestätigung erneut', async () => {
    document.cookie = 'csrftoken=abc'
    const bodies: unknown[] = []
    let first = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit = {}) => {
        bodies.push(init.body)
        if (first) {
          first = false
          return new Response(JSON.stringify({ step_up: 'code' }), { status: 403 })
        }
        return new Response(JSON.stringify({ id: 7 }), { status: 201 })
      }),
    )
    const asked = vi.fn(async () => true)
    setStepUpHandler(asked)
    const file = new File(['{"kind": "department"}'], 'zug.json', { type: 'application/json' })
    const job = await transferApi.upload({ org: 3 }, file, { name: 'Neuzug' })
    expect(asked).toHaveBeenCalledOnce()
    expect(job).toEqual({ id: 7 })
    expect(bodies).toHaveLength(2)
    const again = bodies[1] as FormData
    expect(again).toBeInstanceOf(FormData)
    expect((again.get('file') as File).name).toBe('zug.json')
    expect(again.get('name')).toBe('Neuzug')
  })
})
