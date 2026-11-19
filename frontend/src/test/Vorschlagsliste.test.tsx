// Vorschlagslisten im HUBIplan-Design (Ralf 19.11.2026, Termin › Ort): <datalist> zeichnet der
// Browser selbst, je nach System schwarz und ungestaltet. Felder mit Vorschlägen nehmen deshalb
// SuggestInput (bzw. Field mit `suggestions`). Bedienung nach dem ARIA-Muster Combobox/Listbox.
import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Field } from '../components/ui.tsx'
import { matchSuggestions } from '../components/suggest.ts'

const quellen = import.meta.glob(['../**/*.tsx', '!../test/**', '!../**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const ORTE = [
  { value: 'Bürgerhaus', detail: 'Musterweg 1, 12345 Musterstadt' },
  { value: 'Bürgerhaus, Saal', detail: 'Musterweg 1, 12345 Musterstadt' },
  { value: 'Festplatz' },
]

function Probe({ onKey }: { onKey?: () => void }) {
  const [wert, setWert] = useState('')
  return (
    // Esc in der Liste darf den Dialog drumherum nicht schließen
    <div onKeyDown={(e) => e.key === 'Escape' && onKey?.()}>
      <Field
        label="Ort"
        value={wert}
        suggestions={ORTE}
        onChange={(e) => setWert(e.target.value)}
      />
      <output>{wert}</output>
    </div>
  )
}

describe('Vorschlagsliste', () => {
  it('kein <datalist> mehr im Frontend', () => {
    const treffer = Object.entries(quellen)
      .filter(([, text]) => /<datalist\b/.test(text))
      .map(([datei]) => datei)
    expect(treffer).toEqual([])
  })

  it('filtert nach Teiltext, zeigt bei leerem oder genauem Treffer alle', () => {
    expect(matchSuggestions(ORTE, '').length).toBe(3)
    expect(matchSuggestions(ORTE, 'saal').map((s) => s.value)).toEqual(['Bürgerhaus, Saal'])
    expect(matchSuggestions(ORTE, 'musterstadt').length).toBe(2)
    expect(matchSuggestions(ORTE, 'Festplatz').length).toBe(3)
  })

  it('Pfeiltasten und Eingabe wählen, Esc schließt nur die Liste', async () => {
    const esc = vi.fn()
    render(<Probe onKey={esc} />)
    const feld = screen.getByRole('combobox', { name: 'Ort' })
    expect(feld).toHaveAttribute('aria-expanded', 'false')
    feld.focus()
    const user = userEvent.setup()
    await user.keyboard('{ArrowDown}')
    expect(feld).toHaveAttribute('aria-expanded', 'true')
    const liste = screen.getByRole('listbox')
    expect(within(liste).getAllByRole('option')).toHaveLength(3)
    await user.keyboard('{ArrowDown}')
    const aktiv = document.getElementById(feld.getAttribute('aria-activedescendant')!)!
    expect(aktiv).toHaveAttribute('aria-selected', 'true')
    expect(aktiv).toHaveTextContent('Bürgerhaus, Saal')
    await user.keyboard('{Enter}')
    expect(feld).toHaveValue('Bürgerhaus, Saal')
    expect(feld).toHaveAttribute('aria-expanded', 'false')

    await user.keyboard('{ArrowDown}')
    expect(feld).toHaveAttribute('aria-expanded', 'true')
    await user.keyboard('{Escape}')
    expect(feld).toHaveAttribute('aria-expanded', 'false')
    expect(esc).not.toHaveBeenCalled()
    // bei geschlossener Liste geht Esc weiter an den Dialog
    await user.keyboard('{Escape}')
    expect(esc).toHaveBeenCalledTimes(1)
  })

  it('Tippen filtert, Klick übernimmt, freie Eingabe bleibt', async () => {
    render(<Probe />)
    const feld = screen.getByRole('combobox', { name: 'Ort' })
    const user = userEvent.setup()
    await user.type(feld, 'fest')
    const optionen = within(screen.getByRole('listbox')).getAllByRole('option')
    expect(optionen).toHaveLength(1)
    await user.click(optionen[0])
    expect(feld).toHaveValue('Festplatz')
    await user.clear(feld)
    await user.type(feld, 'Zeltwiese')
    expect(feld).toHaveValue('Zeltwiese')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('Knopf am Feld öffnet die Liste', () => {
    render(<Probe />)
    fireEvent.click(screen.getByRole('button', { name: 'Vorschläge zeigen', hidden: true }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })
})
