import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Todo } from '../api/todos.ts'
import { TodoSharing } from '../components/TodoSharing.tsx'
import { TodoLocalNote } from '../components/TodoDistribution.tsx'
import { noteChange, redo, resetUndo, undo } from '../components/undo.ts'
import { fakeApi } from './fakeApi.ts'

afterEach(resetUndo)

describe('Aufgaben über Einheiten hinweg', () => {
  it('fügt gleichnamige Rollen je Zieleinheit ausdrücklich mit eigenen Ausgaben hinzu', async () => {
    let saved: { shares: { role: number; target_org: number }[]; per_unit: boolean } | undefined
    const todo = {
      id: 1,
      organization: 7,
      department: null,
      version: 1,
      shares: [],
    } as unknown as Todo
    fakeApi({
      'GET /api/orgs/7/todos/choices/': () => ({
        status: 200,
        body: {
          users: [],
          roles: [],
          units: [
            {
              key: '7:0',
              organization: 7,
              department: null,
              name: 'Dachverband',
              users: [],
              roles: [{ id: 10, name: 'Vorstand' }],
            },
            {
              key: '8:0',
              organization: 8,
              department: null,
              name: 'Verein A',
              users: [],
              roles: [{ id: 20, name: 'Vorstand' }],
            },
            {
              key: '9:0',
              organization: 9,
              department: null,
              name: 'Verein B',
              users: [],
              roles: [{ id: 30, name: 'Vorstand' }],
            },
          ],
        },
      }),
      'PATCH /api/orgs/7/todos/1/': (init) => {
        saved = JSON.parse(String(init?.body))
        return { status: 200, body: { ...todo, ...saved, version: 2 } }
      },
    })
    const onSaved = vi.fn()
    render(<TodoSharing base="/api/orgs/7/todos/" todo={todo} onSaved={onSaved} />)
    await screen.findByRole('option', { name: 'Dachverband' })
    await userEvent.selectOptions(screen.getByLabelText('Empfänger'), 'r:10')
    await userEvent.click(
      screen.getByRole('button', { name: 'Rolle „Vorstand“ in 2 Zieleinheiten hinzufügen' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Freigaben speichern' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(saved?.per_unit).toBe(true)
    expect(saved?.shares.map((share) => [share.role, share.target_org])).toEqual([
      [20, 8],
      [30, 9],
    ])
  })

  it('speichert eine lokale Notiz ohne zentrale Felder und erhält eine zentrale Versionsänderung', async () => {
    let saved: Record<string, unknown> | undefined
    const todo = {
      id: 1,
      version: 1,
      title: 'Quelle',
      local_note: '',
      can_edit: true,
      distributed: true,
    } as Todo
    fakeApi({
      'PATCH /api/orgs/8/todos/1/': (init) => {
        saved = JSON.parse(String(init?.body))
        return { status: 200, body: { ...todo, ...saved, version: 3 } }
      },
    })
    const onSaved = vi.fn()
    const view = render(<TodoLocalNote base="/api/orgs/8/todos/" todo={todo} onSaved={onSaved} />)
    await userEvent.type(screen.getByLabelText('Lokale Notiz'), 'Nur hier')
    view.rerender(
      <TodoLocalNote
        base="/api/orgs/8/todos/"
        todo={{ ...todo, version: 2, title: 'Neue Quelle' }}
        onSaved={onSaved}
      />,
    )
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(saved).toEqual({ local_note: 'Nur hier', version: 2 })
  })

  it('führt Rücknahme und Wiederherstellung im berechtigten Aufgabenbereich aus', async () => {
    const calls = fakeApi({
      'POST /api/orgs/8/todos/12/changes/alt/undo/': () => ({
        status: 200,
        body: { change_set: 'neu' },
      }),
      'POST /api/orgs/8/todos/12/changes/neu/undo/': () => ({
        status: 200,
        body: { change_set: 'wieder' },
      }),
    })
    noteChange(
      '/api/orgs/8/todos/12/',
      200,
      new Headers({ 'X-Change-Set': 'alt', 'X-Change-Undoable': '1', 'X-Change-Task': '12' }),
    )
    await undo('/api/orgs/8')
    await redo('/api/orgs/8')
    expect(calls.map((call) => call.key)).toEqual([
      'POST /api/orgs/8/todos/12/changes/alt/undo/',
      'POST /api/orgs/8/todos/12/changes/neu/undo/',
    ])
  })
})
