import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ActionMenu, PageHeader, Segmented } from '../components/PageHeader.tsx'
import { NavTrailContext, navTrail, trailTitle } from '../components/navTrail.ts'
import type { NavTrailValue } from '../components/navTrail.ts'

const FINANZEN = { path: '/finanzen', label: 'Finanzen' }
const SECTIONS = [
  { to: '/finanzen', label: 'Übersicht' },
  { to: '/finanzen/rechnungen', label: 'Rechnungen' },
  { to: '/finanzen/kassenbuch', label: 'Kassenbuch' },
]
// Reiter, die die Rechnungsseite selbst anmeldet (erster = Seite selbst)
const INVOICE_TABS = [
  { to: '/finanzen/rechnungen', label: 'Rechnungen' },
  { to: '/finanzen/rechnungen/mahnungen', label: 'Mahnungen' },
]

function renderHeader(value: NavTrailValue, node: React.ReactNode, path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <NavTrailContext.Provider value={value}>{node}</NavTrailContext.Provider>
    </MemoryRouter>,
  )
}

describe('Pfad aus der Menüstruktur', () => {
  it('erste Ebene: nur das Modul, Übersicht gehört zum Modul', () => {
    expect(navTrail('/finanzen', FINANZEN, SECTIONS, [])).toEqual([
      { to: '/finanzen', label: 'Finanzen' },
    ])
  })

  it('zweite und dritte Ebene aus Seitenleiste und angemeldeten Reitern', () => {
    expect(navTrail('/finanzen/rechnungen', FINANZEN, SECTIONS, [INVOICE_TABS])).toEqual([
      { to: '/finanzen', label: 'Finanzen' },
      { to: '/finanzen/rechnungen', label: 'Rechnungen' },
    ])
    const deep = navTrail('/finanzen/rechnungen/mahnungen/', FINANZEN, SECTIONS, [INVOICE_TABS])
    expect(deep.map((i) => i.label)).toEqual(['Finanzen', 'Rechnungen', 'Mahnungen'])
    expect(trailTitle(deep)).toBe('Mahnungen · Rechnungen · Finanzen')
  })

  it('ohne Modul leer', () => {
    expect(navTrail('/hilfe', null, [], [])).toEqual([])
    expect(trailTitle([])).toBeNull()
  })
})

describe('PageHeader', () => {
  const deep: NavTrailValue = {
    trail: [
      { to: '/finanzen', label: 'Finanzen' },
      { to: '/finanzen/rechnungen', label: 'Rechnungen' },
      { to: '/finanzen/rechnungen/mahnungen', label: 'Mahnungen' },
    ],
    unit: null,
  }

  it('h1 = Menüpunkt, Pfad mit aktueller Seite ohne Link', () => {
    renderHeader(deep, <PageHeader />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Mahnungen')
    const nav = screen.getByRole('navigation', { name: 'Pfad' })
    const items = within(nav).getAllByRole('listitem')
    expect(items.map((i) => i.textContent)).toEqual(['Finanzen', 'Rechnungen', 'Mahnungen'])
    expect(within(nav).getByRole('link', { name: 'Finanzen' })).toHaveAttribute('href', '/finanzen')
    expect(within(items[2]).queryByRole('link')).toBeNull()
    expect(within(items[2]).getByText('Mahnungen')).toHaveAttribute('aria-current', 'page')
    // Handy: ein Link zur Elternseite (auf dem Desktop ausgeblendet)
    const back = nav.querySelector('.page-header-back')
    expect(back).toHaveAttribute('aria-label', 'Zurück zu Rechnungen')
    expect(back).toHaveAttribute('href', '/finanzen/rechnungen')
  })

  it('erste Ebene ohne Pfad, Einheit als Kennzeichen', () => {
    renderHeader(
      { trail: [{ to: '/termine', label: 'Termine' }], unit: 'Jägerkorps' },
      <PageHeader />,
    )
    expect(screen.queryByRole('navigation', { name: 'Pfad' })).toBeNull()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1).toHaveTextContent(/^Termine$/)
    expect(screen.getByText('Jägerkorps')).toHaveClass('page-header-unit')
  })

  it('Objektseite: eigener Titel, ganzer Pfad verlinkt, Seitentitel mit Name', () => {
    renderHeader(
      { trail: [{ to: '/mitglieder', label: 'Mitglieder' }], unit: null },
      <PageHeader title="Max Mustermann" extra={<span>Nr. 17</span>} />,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Max Mustermann')
    expect(screen.getByRole('link', { name: 'Mitglieder' })).toBeInTheDocument()
    expect(screen.getByText('Nr. 17')).toBeInTheDocument()
  })

  it('genau eine Hauptaktion, weitere Aktionen im Menü, Löschen zuletzt', async () => {
    const remove = vi.fn()
    const run = vi.fn()
    renderHeader(
      deep,
      <PageHeader
        primary={{ label: 'Mahnlauf vorbereiten', onClick: run }}
        actions={[
          { label: 'Löschen', danger: true, onClick: remove },
          { label: 'Export', href: '/export.csv' },
          false,
        ]}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Mahnlauf vorbereiten' }))
    expect(run).toHaveBeenCalled()
    expect(document.querySelectorAll('.button-primary')).toHaveLength(1)
    const more = screen.getByRole('button', { name: 'Weitere Aktionen' })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(more)
    expect(more).toHaveAttribute('aria-expanded', 'true')
    const list = document.getElementById(more.getAttribute('aria-controls')!)!
    const entries = within(list).getAllByRole('listitem')
    expect(entries.map((e) => e.textContent)).toEqual(['Export', 'Löschen'])
    // Fokus springt in die Liste, Esc schließt und gibt ihn zurück
    expect(within(list).getByRole('link', { name: 'Export' })).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(more).toHaveAttribute('aria-expanded', 'false')
    expect(more).toHaveFocus()
    await userEvent.click(more)
    await userEvent.click(screen.getByRole('button', { name: 'Löschen' }))
    expect(remove).toHaveBeenCalled()
    expect(more).toHaveAttribute('aria-expanded', 'false')
  })

  it('zwei gleich wichtige Aktionen: ein Knopf mit Auswahl', async () => {
    const income = vi.fn()
    renderHeader(
      { trail: [{ to: '/finanzen/kassenbuch', label: 'Kassenbuch' }], unit: null },
      <PageHeader
        primary={{
          label: 'Neue Buchung',
          items: [
            { label: 'Einnahme', onClick: income },
            { label: 'Ausgabe', onClick: () => undefined },
          ],
        }}
      />,
    )
    const button = screen.getByRole('button', { name: 'Neue Buchung' })
    expect(button).toHaveClass('button-primary')
    await userEvent.click(button)
    await userEvent.click(screen.getByRole('button', { name: 'Einnahme' }))
    expect(income).toHaveBeenCalled()
  })

  it('ActionMenu schließt beim Klick daneben', async () => {
    render(
      <MemoryRouter>
        <p>daneben</p>
        <ActionMenu actions={[{ label: 'Drucken', onClick: () => undefined }]} />
      </MemoryRouter>,
    )
    const more = screen.getByRole('button', { name: 'Weitere Aktionen' })
    await userEvent.click(more)
    expect(screen.getByRole('button', { name: 'Drucken' })).toBeInTheDocument()
    await userEvent.click(screen.getByText('daneben'))
    expect(screen.queryByRole('button', { name: 'Drucken' })).toBeNull()
  })
})

describe('Segmented', () => {
  it('zeigt die Ansicht als Zustand mit aria-pressed', async () => {
    const change = vi.fn()
    render(
      <Segmented
        label="Ansicht"
        value="monat"
        onChange={change}
        options={[
          { value: 'liste', label: 'Liste' },
          { value: 'monat', label: 'Monat' },
        ]}
      />,
    )
    const group = screen.getByRole('group', { name: 'Ansicht' })
    expect(within(group).getByRole('button', { name: 'Monat' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(within(group).getByRole('button', { name: 'Liste' })).not.toHaveClass('button-primary')
    await userEvent.click(within(group).getByRole('button', { name: 'Liste' }))
    expect(change).toHaveBeenCalledWith('liste')
  })
})
