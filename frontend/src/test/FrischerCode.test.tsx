// Frischer Code vor heiklen Aktionen (Gesamtaudit 10.11., Frage 1)
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ApiError, api, setStepUpHandler } from '../api/client.ts'
import { installStepUp } from '../components/stepUp.ts'

type Call = { url: string; method: string; body: unknown }

function server(answers: ((call: Call) => [number, unknown] | null)[]) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const call = {
        url,
        method: init.method ?? 'GET',
        body: init.body ? JSON.parse(String(init.body)) : undefined,
      }
      calls.push(call)
      for (const answer of answers) {
        const result = answer(call)
        if (result)
          return new Response(JSON.stringify(result[1]), {
            status: result[0],
            headers: { 'Content-Type': 'application/json' },
          })
      }
      return new Response('{}', { status: 404 })
    }),
  )
  return calls
}

describe('Frischer Code', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=abc'
    installStepUp()
  })
  afterEach(() => {
    setStepUpHandler(null)
    vi.unstubAllGlobals()
  })

  it('fragt nach dem Code und sendet die Anfrage danach erneut', async () => {
    let confirmed = false
    const calls = server([
      (c) =>
        c.url === '/api/me/confirm/'
          ? (c.body as { code: string }).code === '123456'
            ? ((confirmed = true), [200, { fresh: true }])
            : [403, { detail: 'Der Code stimmt nicht.' }]
          : null,
      (c) =>
        c.url === '/api/orgs/1/export/'
          ? confirmed
            ? [201, { id: 7 }]
            : [403, { detail: 'Bitte Code.', step_up: 'code' }]
          : null,
    ])
    const user = userEvent.setup()
    const result = api.post<{ id: number }>('/api/orgs/1/export/', { kind: 'full' })

    let dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Code'), '000000')
    await user.click(within(dialog).getByRole('button', { name: 'Bestätigen' }))
    // Falscher Code: Dialog kommt mit Hinweis wieder
    dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Der Code stimmt nicht.')
    const input = within(dialog).getByLabelText('Code')
    expect(input).toHaveAttribute('autocomplete', 'one-time-code')
    await user.type(input, '123456')
    await user.click(within(dialog).getByRole('button', { name: 'Bestätigen' }))

    expect(await result).toEqual({ id: 7 })
    expect(calls.filter((c) => c.url === '/api/orgs/1/export/')).toHaveLength(2)
  })

  it('Abbrechen lässt die Aktion mit der Meldung des Servers scheitern', async () => {
    server([() => [403, { detail: 'Bitte dein Passwort.', step_up: 'password' }]])
    const user = userEvent.setup()
    const result = api.post('/api/orgs/1/assignments/', {}).catch((e: unknown) => e)
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Passwort')).toHaveAttribute('type', 'password')
    await user.click(within(dialog).getByRole('button', { name: 'Abbrechen' }))
    const err = (await result) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Bitte dein Passwort.')
  })
})
