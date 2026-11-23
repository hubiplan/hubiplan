// Bearbeiten direkt am Eintrag (Ralf 23.11.): Das Formular erscheint unter dem bearbeiteten
// Eintrag statt oben auf der Seite, und das erste Feld bekommt den Fokus.
import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EditAt, EditSlot, editKey } from '../components/EditInPlace.tsx'

type Item = { id: number; name: string }
const ITEMS: Item[] = [
  { id: 1, name: 'Sommerfest' },
  { id: 2, name: 'Herbstkonzert' },
  { id: 3, name: 'Adventsmarkt' },
]

function Liste({ items = ITEMS }: { items?: Item[] }) {
  const [editing, setEditing] = useState<Item | 'new' | null>(null)
  return (
    <section>
      <button onClick={() => setEditing('new')}>Neu</button>
      {editing && (
        <EditAt at={editing === 'new' ? null : editKey('probe', editing.id)}>
          <form aria-label="Formular">
            <label>
              Name
              <input defaultValue={editing === 'new' ? '' : editing.name} />
            </label>
          </form>
        </EditAt>
      )}
      <ul>
        {items.map((i) => (
          <li key={i.id} data-testid={`eintrag-${i.id}`}>
            {i.name}
            <button onClick={() => setEditing(i)}>{`${i.name} bearbeiten`}</button>
            <EditSlot id={editKey('probe', i.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

describe('Bearbeiten direkt am Eintrag', () => {
  it('zeigt das Formular unter dem angeklickten Eintrag und fokussiert das erste Feld', async () => {
    render(<Liste />)
    fireEvent.click(screen.getByRole('button', { name: 'Herbstkonzert bearbeiten' }))
    const form = await screen.findByRole('form', { name: 'Formular' })
    expect(screen.getByTestId('eintrag-2')).toContainElement(form)
    expect(screen.getByTestId('eintrag-1')).not.toContainElement(form)
    expect(within(form).getByLabelText('Name')).toHaveValue('Herbstkonzert')
    expect(within(form).getByLabelText('Name')).toHaveFocus()
  })

  it('wandert beim Wechsel zum nächsten Eintrag mit', async () => {
    render(<Liste />)
    fireEvent.click(screen.getByRole('button', { name: 'Herbstkonzert bearbeiten' }))
    await screen.findByRole('form', { name: 'Formular' })
    fireEvent.click(screen.getByRole('button', { name: 'Adventsmarkt bearbeiten' }))
    const form = await screen.findByRole('form', { name: 'Formular' })
    expect(screen.getByTestId('eintrag-3')).toContainElement(form)
    expect(screen.getAllByRole('form')).toHaveLength(1)
  })

  it('lässt ein neues Formular an seiner Stelle über der Liste', async () => {
    render(<Liste />)
    fireEvent.click(screen.getByRole('button', { name: 'Neu' }))
    const form = await screen.findByRole('form', { name: 'Formular' })
    for (const i of ITEMS) expect(screen.getByTestId(`eintrag-${i.id}`)).not.toContainElement(form)
    expect(within(form).getByLabelText('Name')).toHaveFocus()
  })

  it('zeigt das Formular an seiner Stelle, wenn der Eintrag nicht in der Liste steht', async () => {
    function Ausgefiltert() {
      return (
        <section>
          <EditAt at={editKey('probe', 99)}>
            <form aria-label="Formular">
              <input aria-label="Name" />
            </form>
          </EditAt>
          <EditSlot id={editKey('probe', 1)} />
        </section>
      )
    }
    render(<Ausgefiltert />)
    expect(await screen.findByRole('form', { name: 'Formular' })).toBeInTheDocument()
  })
})
