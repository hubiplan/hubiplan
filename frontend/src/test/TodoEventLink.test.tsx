import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { EventTaskRow } from '../components/TodoEventLink.tsx'

vi.mock('../org/OrgContext.tsx', () => ({
  useOptionalOrg: () => ({ active: { permissions: ['todos.view'] } }),
}))

describe('Aufgaben am Termin', () => {
  it('übergibt Termin und Zieleinheit an die Aufgabenansicht', () => {
    render(
      <MemoryRouter>
        <EventTaskRow base="/api/depts/9/events/" eventId={42} />
      </MemoryRouter>,
    )
    expect(
      screen.getByRole('link', { name: 'Aufgaben zu diesem Termin anzeigen' }),
    ).toHaveAttribute('href', '/aufgaben?termin=42&abteilung=9')
    expect(screen.getByRole('link', { name: 'Aufgabe zu diesem Termin anlegen' })).toHaveAttribute(
      'href',
      '/aufgaben?termin=42&abteilung=9&neu=1',
    )
    // Beide Ziele als gleichartige Knöpfe in der Zeile „Aufgaben“ (Ralf 15.11.2026)
    expect(screen.getByRole('group', { name: 'Aufgaben' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Aufgabe zu diesem Termin anlegen' })).toHaveClass(
      'button',
    )
    expect(screen.getByRole('link', { name: 'Aufgaben zu diesem Termin anzeigen' })).toHaveClass(
      'button',
    )
  })
  it('bietet im Mitgliederkalender keinen Link in die Verwaltung an', () => {
    render(
      <MemoryRouter>
        <EventTaskRow base="/api/portal/9/events/" eventId={42} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
