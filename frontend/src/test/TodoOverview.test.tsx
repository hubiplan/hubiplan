import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { OrphanTasks } from '../components/OrphanTasks.tsx'
import { TodoRemoteInbox } from '../components/TodoRemote.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const base = '/api/orgs/7/todos/'

describe('Aufgabenübersicht', () => {
  it('blendet leere Hinweise aus und hält die Aufbewahrung unter Verwaltung erreichbar', async () => {
    let purge = false
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['todos.view', 'todos.edit', 'roles.edit'] })],
      }),
      [`GET ${base}`]: () => ({ status: 200, body: { items: [] } }),
      [`GET ${base}orphans/`]: () => ({ status: 200, body: { items: [] } }),
      [`GET ${base}remote/`]: () => ({ status: 200, body: { items: [] } }),
      [`GET ${base}cleanup/`]: () => ({ status: 200, body: { purge_done: purge } }),
      [`PATCH ${base}cleanup/`]: (init) => {
        purge = JSON.parse(String(init?.body)).purge_done
        return { status: 200, body: { purge_done: purge } }
      },
    })
    render(
      <MemoryRouter initialEntries={['/aufgaben']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    await screen.findByText('Keine Aufgaben vorhanden.')
    expect(screen.queryByText('Aufgaben aus anderen Installationen')).not.toBeInTheDocument()
    expect(screen.queryByText('Aufgaben ohne verantwortliches Konto')).not.toBeInTheDocument()
    const administration = screen.getByText('Verwaltung').closest('details')!
    expect(administration).not.toHaveAttribute('open')
    const user = userEvent.setup()
    await user.click(screen.getByText('Verwaltung'))
    const setting = await screen.findByRole('checkbox', { name: /nach 12 Monaten/ })
    await user.click(setting)
    await waitFor(() => expect(purge).toBe(true))
    expect(setting).toBeChecked()
  })

  it('zählt eingehende Aufgaben und entfernt den Hinweis nach der letzten Übernahme', async () => {
    const offer = {
      id: 31,
      from: 'Musterverband',
      title: 'Unterlagen prüfen',
      description: '',
      mode: 'copy',
    }
    let items = [offer]
    fakeApi({
      [`GET ${base}remote/`]: () => ({ status: 200, body: { items } }),
      [`POST ${base}remote/31/adopt/`]: () => {
        items = []
        return { status: 200, body: { id: 50 } }
      },
    })
    const saved = vi.fn()
    render(<TodoRemoteInbox base={base} onSaved={saved} />)
    const summary = await screen.findByText('Aufgaben aus anderen Installationen')
    expect(summary.querySelector('.badge')).toHaveTextContent('1')
    const user = userEvent.setup()
    await user.click(summary)
    await user.click(screen.getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(saved).toHaveBeenCalledOnce())
    await waitFor(() =>
      expect(screen.queryByText('Aufgaben aus anderen Installationen')).not.toBeInTheDocument(),
    )
  })

  it('entfernt den verwaisten Hinweis nach Übernahme der letzten Verantwortung', async () => {
    let items = [{ id: 17 }]
    fakeApi({
      [`GET ${base}orphans/`]: () => ({ status: 200, body: { items } }),
      [`POST ${base}17/take-over/`]: () => {
        items = []
        return { status: 200, body: {} }
      },
    })
    const saved = vi.fn()
    render(<OrphanTasks base={base} onSaved={saved} />)
    const summary = await screen.findByText('Aufgaben ohne verantwortliches Konto')
    expect(summary.querySelector('.badge')).toHaveTextContent('1')
    const user = userEvent.setup()
    await user.click(summary)
    await user.click(screen.getByRole('button', { name: 'Verantwortung übernehmen' }))
    await waitFor(() => expect(saved).toHaveBeenCalledOnce())
    await waitFor(() =>
      expect(screen.queryByText('Aufgaben ohne verantwortliches Konto')).not.toBeInTheDocument(),
    )
  })

  it.each(['remote', 'orphans'])(
    'erhält Ladefehler für %s mit einer erneuten Lademöglichkeit',
    async (kind) => {
      let failed = true
      fakeApi({
        [`GET ${base}${kind}/`]: () =>
          failed
            ? { status: 503, body: { detail: 'Vorübergehend nicht erreichbar' } }
            : { status: 200, body: { items: [] } },
      })
      render(
        kind === 'remote' ? (
          <TodoRemoteInbox base={base} onSaved={() => {}} />
        ) : (
          <OrphanTasks base={base} onSaved={() => {}} />
        ),
      )
      const error = await screen.findByRole('alert')
      expect(error).toHaveTextContent('Vorübergehend nicht erreichbar')
      const summary = error.closest('details')!.querySelector('summary')!
      expect(summary.closest('details')).toHaveAttribute('open')
      const user = userEvent.setup()
      failed = false
      await user.click(screen.getByRole('button', { name: 'Erneut laden' }))
      await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
      expect(summary).not.toBeInTheDocument()
    },
  )
})
