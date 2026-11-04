import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Todo } from '../api/todos.ts'
import { followingChoice, TodoSeries } from '../components/TodoSeries.tsx'
import { fakeApi } from './fakeApi.ts'

describe('Aufgabenserie', () => {
  it('speichert Intervall und Endbedingung mit aktueller Aufgabenversion', async () => {
    let saved: Record<string, unknown> | undefined
    fakeApi({
      'GET /api/orgs/7/todos/1/': () => ({ status: 200, body: { version: 4 } }),
      'PATCH /api/orgs/7/todos/1/series/': (init) => {
        saved = JSON.parse(String(init?.body))
        return { status: 200, body: { version: 5 } }
      },
    })
    const onSaved = vi.fn()
    const todo = {
      id: 1,
      version: 2,
      due_date: '2032-01-31',
      status: 'open',
      can_edit: true,
    } as Todo
    render(<TodoSeries base="/api/orgs/7/todos/" todo={todo} trash={false} onSaved={onSaved} />)
    await userEvent.click(screen.getByText('Wiederholen'))
    await userEvent.selectOptions(screen.getByLabelText('Wiederholregel'), 'weekly')
    await userEvent.clear(screen.getByLabelText('Alle n Zeiträume'))
    await userEvent.type(screen.getByLabelText('Alle n Zeiträume'), '2')
    await userEvent.type(
      screen.getByLabelText('Anzahl einschließlich erster Ausgabe (optional)'),
      '5',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Serie beginnen' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(saved).toMatchObject({
      version: 4,
      repeat: 'weekly',
      interval: 2,
      count: 5,
      ends_on: null,
    })
  })

  it('lässt die Auswahl nur dieser Ausgabe ausdrücklich abbrechen', async () => {
    const selected = followingChoice()
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(await selected).toBeNull()
  })
})
