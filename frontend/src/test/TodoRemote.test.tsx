import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { TodoRemote } from '../components/TodoRemote.tsx'
import type { Todo } from '../api/todos.ts'
import { fakeApi } from './fakeApi.ts'

it('gibt die gewählte gemeinsame Variante ausdrücklich frei und behält den gespeicherten Stand', async () => {
  const user = userEvent.setup()
  let state = {
    version: 3,
    couplings: [{ id: 8, name: 'Musterverband', enabled: true }],
    shares: [] as object[],
  }
  let written: Record<string, unknown> = {}
  fakeApi({
    'GET /api/orgs/7/todos/12/remote/': () => ({ status: 200, body: state }),
    'PUT /api/orgs/7/todos/12/remote/': (init) => {
      written = JSON.parse(String(init?.body))
      state = { ...state, version: 4, shares: [{ ...written, progress: [] }] }
      return { status: 200, body: state }
    },
  })
  const saved = vi.fn()
  render(
    <TodoRemote base="/api/orgs/7/todos/" todo={{ id: 12, version: 3 } as Todo} onSaved={saved} />,
  )
  await user.click(screen.getByText('Mit anderer Installation teilen'))
  await user.click(await screen.findByLabelText('Aufgabe für diese Installation freigeben'))
  await user.selectOptions(screen.getByLabelText('Erledigung zwischen Installationen'), 'common')
  await user.click(screen.getByRole('button', { name: 'Freigabe speichern' }))
  await waitFor(() => expect(saved).toHaveBeenCalledOnce())
  expect(written).toEqual({
    version: 3,
    coupling: 8,
    active: true,
    mode: 'common',
    can_complete: true,
    following: false,
  })
  expect(screen.getByLabelText('Erledigung zwischen Installationen')).toHaveValue('common')
  expect(screen.getByLabelText('Erledigung zwischen Installationen')).toBeDisabled()
})
