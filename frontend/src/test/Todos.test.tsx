import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

function setup(path = '/aufgaben') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Eigene Aufgaben', () => {
  it('öffnet einen Erinnerungslink in der angegebenen berechtigten Einheit', async () => {
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [
          testOrg({ id: 7, permissions: ['todos.view'] }),
          testOrg({ id: 8, permissions: ['todos.view'] }),
        ],
      }),
      'GET /api/orgs/7/todos/': () => ({ status: 200, body: { items: [] } }),
      'GET /api/orgs/8/todos/': () => ({
        status: 200,
        body: {
          items: [
            {
              id: 50,
              title: 'Aufgabe der anderen Einheit',
              description: '',
              status: 'open',
              can_edit: false,
              can_delete: false,
              shared: true,
              due_date: null,
            },
          ],
        },
      }),
    })
    setup('/aufgaben?aufgabe=50&einheit=8')
    expect(
      await screen.findByRole('button', { name: 'Aufgabe der anderen Einheit' }),
    ).toBeInTheDocument()
  })

  it('erreicht Aufgaben auch nur mit einer Abteilungsrolle', async () => {
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({ status: 200, body: [] }),
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: {
          portal: [],
          departments: [
            {
              id: 5,
              name: 'Abteilung Beispiel',
              club_id: 7,
              club_name: 'Musterverein',
              label: 'Abteilung',
              permissions: ['todos.view'],
              theme: testOrg().theme,
            },
          ],
        },
      }),
      'GET /api/depts/5/todos/': () => ({
        status: 200,
        body: {
          items: [
            {
              id: 51,
              title: 'Material für die Abteilung',
              status: 'open',
              can_edit: true,
              can_delete: true,
              shared: false,
              due_date: null,
            },
          ],
        },
      }),
    })
    setup()
    expect(
      await screen.findByRole('button', { name: 'Material für die Abteilung' }),
    ).toBeInTheDocument()
  })
  it('legt mit Leserecht eine Aufgabe an und zeigt sie in der Liste', async () => {
    let items: unknown[] = []
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['todos.view'] })],
      }),
      'GET /api/orgs/7/todos/': () => ({ status: 200, body: { items } }),
      'POST /api/orgs/7/todos/': (init) => {
        const created = {
          ...JSON.parse(String(init?.body)),
          id: 1,
          version: 1,
          status: 'open',
          can_edit: true,
          can_delete: true,
          shared: false,
        }
        items = [created]
        return { status: 201, body: created }
      },
    })
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Neue Aufgabe' }))
    await userEvent.type(screen.getByLabelText('Titel'), 'Material bestellen')
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }))
    expect(await screen.findByRole('button', { name: 'Material bestellen' })).toBeInTheDocument()
  })

  it('bietet einer geteilten Leserin keinen Haken zum Erledigen', async () => {
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['todos.view'] })],
      }),
      'GET /api/orgs/7/todos/': () => ({
        status: 200,
        body: {
          items: [
            {
              id: 1,
              title: 'Nur lesen',
              status: 'open',
              can_edit: false,
              can_delete: false,
              shared: true,
              due_date: null,
            },
          ],
        },
      }),
    })
    setup()
    await screen.findByRole('button', { name: 'Nur lesen' })
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Erledigt' })).toBeDisabled())
    expect(screen.queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument()
  })

  it('speichert offene Eingaben vor dem Erledigen und erhält die neue Version', async () => {
    let task = {
      id: 1,
      title: 'Vorbereiten',
      description: '',
      due_date: null,
      due_time: null,
      status: 'open',
      version: 1,
      can_edit: true,
      can_delete: true,
      shared: false,
    }
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['todos.view'] })],
      }),
      'GET /api/orgs/7/todos/': () => ({ status: 200, body: { items: [task] } }),
      'GET /api/orgs/7/todos/1/': () => ({ status: 200, body: task }),
      'PATCH /api/orgs/7/todos/1/': (init) => {
        const values = JSON.parse(String(init?.body))
        if (values.version !== task.version)
          return { status: 409, body: { detail: 'Veraltete Fassung' } }
        task = { ...task, ...values, version: task.version + 1 }
        return { status: 200, body: task }
      },
    })
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Vorbereiten' }))
    await userEvent.type(screen.getByLabelText('Beschreibung'), 'Erste Notiz')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Erledigt' }))
    await waitFor(() => expect(task.status).toBe('done'))
    expect(task.description).toBe('Erste Notiz')
    await userEvent.type(screen.getByLabelText('Beschreibung'), ' ergänzt')
    await waitFor(() => expect(task.description).toBe('Erste Notiz ergänzt'))
  })
})
