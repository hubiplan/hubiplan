import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { EventTaskLink } from '../components/TodoEventLink.tsx'

vi.mock('../org/OrgContext.tsx', () => ({
  useOrg: () => ({ active: { permissions: ['todos.view'] } }),
}))

describe('Aufgaben am Termin', () => {
  it('übergibt Termin und Zieleinheit an die Aufgabenansicht', () => {
    render(
      <MemoryRouter>
        <EventTaskLink base="/api/depts/9/events/" eventId={42} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Aufgaben zu diesem Termin' })).toHaveAttribute(
      'href',
      '/aufgaben?termin=42&abteilung=9',
    )
    expect(screen.getByRole('link', { name: 'Aufgabe zu diesem Termin anlegen' })).toHaveAttribute(
      'href',
      '/aufgaben?termin=42&abteilung=9&neu=1',
    )
  })
  it('bietet im Mitgliederkalender keinen Link in die Verwaltung an', () => {
    render(
      <MemoryRouter>
        <EventTaskLink base="/api/portal/9/events/" eventId={42} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
