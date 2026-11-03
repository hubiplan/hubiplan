import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

function setup() {
  render(
    <MemoryRouter initialEntries={['/aufgaben']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Eigene Aufgaben', () => {
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
})
