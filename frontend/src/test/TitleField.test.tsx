import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { TitleField } from '../components/TitleField.tsx'

function Form({ start = '' }: { start?: string }) {
  const [value, setValue] = useState(start)
  return (
    <>
      <TitleField value={value} onChange={setValue} />
      <output>{value}</output>
    </>
  )
}

describe('Titel (Auswahlliste oder frei)', () => {
  it('wählt einen üblichen Titel aus der Liste', async () => {
    render(<Form />)
    const select = screen.getByLabelText('Titel')
    expect(select).toHaveValue('')
    await userEvent.selectOptions(select, 'Prof. Dr.')
    expect(screen.getByRole('status')).toHaveTextContent('Prof. Dr.')
    expect(screen.queryByLabelText('Anderer Titel')).toBeNull()
  })

  it('nimmt mit „anderer Titel …“ einen eigenen Titel auf', async () => {
    render(<Form start="Dr." />)
    await userEvent.selectOptions(screen.getByLabelText('Titel'), 'anderer Titel …')
    const free = screen.getByLabelText('Anderer Titel')
    // der bisherige Titel steht zum Bearbeiten im Textfeld
    expect(free).toHaveValue('Dr.')
    await userEvent.clear(free)
    await userEvent.type(free, 'Dipl.-Ing.')
    expect(screen.getByRole('status')).toHaveTextContent('Dipl.-Ing.')
  })

  it('zeigt einen gespeicherten freien Titel im Textfeld', () => {
    render(<Form start="Dr. med." />)
    expect(screen.getByLabelText('Titel')).toHaveValue('__anderer__')
    expect(screen.getByLabelText('Anderer Titel')).toHaveValue('Dr. med.')
  })

  it('setzt „kein Titel“ zurück', async () => {
    render(<Form start="Dr." />)
    await userEvent.selectOptions(screen.getByLabelText('Titel'), 'kein Titel')
    expect(screen.getByRole('status')).toHaveTextContent('')
  })
})
