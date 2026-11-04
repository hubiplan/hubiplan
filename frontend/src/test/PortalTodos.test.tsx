import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalTodos } from '../pages/portal/PortalTodos.tsx'
import { fakeApi } from './fakeApi.ts'

describe('Mitgliederaufgaben', () => {
  it('übernimmt ein Angebot mit seiner angezeigten Version', async () => {
    let row = {
      id: 12,
      title: 'Helferdienst',
      description: 'Raum vorbereiten',
      version: 2,
      status: 'open',
      can_complete: false,
      can_claim: true,
      claimed_by_me: false,
      due_label: '',
      attachments: [],
    }
    fakeApi({
      'GET /api/portal/9/todos/': () => ({ status: 200, body: { items: [row] } }),
      'PATCH /api/portal/9/todos/12/': (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ version: 2, action: 'claim' })
        row = { ...row, version: 3, can_complete: true, can_claim: false, claimed_by_me: true }
        return { status: 200, body: row }
      },
    })
    render(
      <MemoryRouter initialEntries={['/mein-bereich/aufgaben?aufgabe=12']}>
        <PortalTodos accessId={9} />
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Aufgabe übernehmen' }))
    expect(await screen.findByRole('button', { name: 'Erledigen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Übernahme zurückgeben' })).toBeInTheDocument()
  })
  it('bietet einer Leserin weder Bearbeiten noch Erledigen an', async () => {
    fakeApi({
      'GET /api/portal/9/todos/': () => ({
        status: 200,
        body: {
          items: [
            {
              id: 12,
              title: 'Nur lesen',
              description: 'Hinweis',
              version: 1,
              status: 'open',
              can_complete: false,
              can_claim: false,
              claimed_by_me: false,
              attachments: [],
            },
          ],
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/mein-bereich/aufgaben?aufgabe=12']}>
        <PortalTodos accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Nur lesen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Erledigen' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
