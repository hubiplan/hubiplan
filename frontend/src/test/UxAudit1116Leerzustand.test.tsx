// UX-Audit 16.11.2026, VW-20: Leere Hauptlisten zeigen den nächsten Schritt oder sagen, wer
// anlegen kann.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DataTable } from '../components/DataTable.tsx'
import { EmptyList } from '../components/EmptyList.tsx'

describe('VW-20 Leerzustand', () => {
  it('bietet mit Schreibrecht die Hauptaktion in der leeren Fläche an', async () => {
    const onClick = vi.fn()
    render(
      <EmptyList
        title="Noch keine Rücklagen."
        canAdd
        action={{ label: 'Neue Rücklage', onClick }}
      />,
    )
    expect(screen.getByText('Noch keine Rücklagen.')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Neue Rücklage' }))
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/Anlegen kann/)).not.toBeInTheDocument()
  })

  it('sagt ohne Schreibrecht, wer anlegen kann, und zeigt keinen Knopf', () => {
    render(
      <EmptyList
        title="Noch keine Rücklagen."
        canAdd={false}
        action={{ label: 'Neue Rücklage', onClick: () => {} }}
      />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(
      screen.getByText('Anlegen kann, wer hier das Recht zum Bearbeiten hat.'),
    ).toBeInTheDocument()
  })

  it('DataTable zeigt den Leerzustand nur ohne Zeilen, nicht bei erfolgloser Suche', async () => {
    const columns = [{ key: 'name', label: 'Name', value: (r: { name: string }) => r.name }]
    const empty = <p>Leer mit Schritt</p>
    const { rerender } = render(
      <DataTable label="Liste" rows={[]} rowKey={(r) => r.name} columns={columns} empty={empty} />,
    )
    expect(screen.getByText('Leer mit Schritt')).toBeInTheDocument()
    rerender(
      <DataTable
        label="Liste"
        rows={[{ name: 'Anna' }]}
        rowKey={(r) => r.name}
        columns={columns}
        empty={empty}
      />,
    )
    expect(screen.queryByText('Leer mit Schritt')).not.toBeInTheDocument()
    expect(screen.getByText('Anna')).toBeInTheDocument()
  })
})
