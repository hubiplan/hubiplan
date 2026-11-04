import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MaterialPicker } from '../pages/materials/MaterialsPage.tsx'
import { fakeApi } from './fakeApi.ts'

describe('Materialauswahl', () => {
  it('wählt einen Suchtreffer per Tastatur ohne zusätzliches Auswahlmenü', async () => {
    const member = { id: 17, title: 'Erika Beispiel' }
    const calls = fakeApi({
      'GET /api/orgs/7/materials/choices/?kind=member&q=Er': () => ({
        status: 200,
        body: { items: [member], more: false },
      }),
    })
    const select = vi.fn()
    render(<MaterialPicker base="/api/orgs/7/materials/" kind="member" onSelect={select} />)
    const user = userEvent.setup()
    const search = screen.getByRole('searchbox', { name: 'Auswahl suchen' })
    expect(calls).toHaveLength(0)
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    await user.type(search, 'Er')
    const result = await screen.findByRole('button', { name: 'Erika Beispiel' })
    await user.tab()
    expect(result).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(select).toHaveBeenCalledWith(member)
    expect(search).toHaveValue('')
    expect(screen.queryByRole('list', { name: 'Suchergebnisse' })).not.toBeInTheDocument()
  })

  it('zeigt leere Ergebnisse und blendet alte Treffer bei einem Suchfehler aus', async () => {
    fakeApi({
      'GET /api/orgs/7/materials/choices/?kind=document&q=AA': () => ({
        status: 200,
        body: { items: [{ id: 9, title: 'Anleitung' }], more: false },
      }),
      'GET /api/orgs/7/materials/choices/?kind=document&q=BB': () => ({
        status: 200,
        body: { items: [], more: false },
      }),
      'GET /api/orgs/7/materials/choices/?kind=document&q=CC': () => ({
        status: 403,
        body: { detail: 'Kein Zugriff.' },
      }),
    })
    render(<MaterialPicker base="/api/orgs/7/materials/" kind="document" onSelect={vi.fn()} />)
    const user = userEvent.setup()
    const search = screen.getByRole('searchbox')
    await user.type(search, 'AA')
    expect(await screen.findByRole('button', { name: 'Anleitung' })).toBeInTheDocument()
    await user.clear(search)
    await user.type(search, 'CC')
    expect(await screen.findByRole('alert')).toHaveTextContent('Kein Zugriff.')
    expect(screen.queryByRole('button', { name: 'Anleitung' })).not.toBeInTheDocument()
    await user.clear(search)
    await user.type(search, 'BB')
    expect(await screen.findByText('Keine passenden Einträge gefunden.')).toBeInTheDocument()
  })
})
