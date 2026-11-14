// Schnellsuche im Kopf (Design „Frisch“ D7): Seiten und Mitglieder, ganz per Tastatur bedienbar.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { matchPages, QuickSearch } from '../components/QuickSearch.tsx'
import { fakeApi } from './fakeApi.ts'

const PAGES = [
  { to: '/', label: 'Startseite' },
  { to: '/termine', label: 'Termine' },
  { to: '/finanzen', label: 'Finanzen' },
  { to: '/finanzen/buchungen', label: 'Buchungen', parent: 'Finanzen' },
  { to: '/einstellungen', label: 'Einstellungen' },
]

function Ort() {
  return <p data-testid="ort">{useLocation().pathname}</p>
}

function aufbau(memberOrg: number | null = null) {
  render(
    <MemoryRouter>
      <QuickSearch pages={PAGES} memberOrg={memberOrg} />
      <Ort />
    </MemoryRouter>,
  )
}

describe('Schnellsuche', () => {
  it('findet Seiten nach Name und Bereich, Wortanfang zuerst, ohne Umlaut-Hürde', () => {
    expect(matchPages(PAGES, 'fin').map((p) => p.label)).toEqual(['Finanzen', 'Buchungen'])
    expect(matchPages(PAGES, 'buch finanz').map((p) => p.to)).toEqual(['/finanzen/buchungen'])
    expect(matchPages([{ to: '/a', label: 'Ämter' }], 'amter').map((p) => p.label)).toEqual([
      'Ämter',
    ])
    expect(matchPages(PAGES, '  ')).toEqual([])
  })

  it('öffnet mit Strg+K, wählt mit Pfeiltasten und springt mit der Eingabetaste', async () => {
    const user = userEvent.setup()
    aufbau()
    await user.keyboard('{Control>}k{/Control}')
    const dialog = screen.getByRole('dialog', { name: 'Schnellsuche' })
    const feld = within(dialog).getByRole('combobox', { name: 'Seite suchen' })
    expect(feld).toHaveFocus()
    await user.type(feld, 'fin')
    const treffer = within(dialog).getAllByRole('option')
    expect(treffer.map((o) => o.textContent)).toEqual(['Finanzen', 'BuchungenFinanzen'])
    expect(treffer[0]).toHaveAttribute('aria-selected', 'true')
    expect(feld).toHaveAttribute('aria-activedescendant', treffer[0].id)
    await user.keyboard('{ArrowDown}')
    expect(within(dialog).getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{Enter}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('ort')).toHaveTextContent('/finanzen/buchungen')
  })

  it('öffnet über den Knopf im Kopf und meldet, wenn nichts passt', async () => {
    const user = userEvent.setup()
    aufbau()
    await user.click(screen.getByRole('button', { name: /Schnellsuche/ }))
    await user.type(screen.getByRole('combobox'), 'xyz')
    expect(screen.getByRole('status')).toHaveTextContent('Nichts gefunden.')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('sucht Mitglieder nur, wenn die Einheit es erlaubt', async () => {
    fakeApi({
      'GET /api/orgs/7/members/?suche=Mus&status=alle&page_size=6': () => ({
        status: 200,
        body: {
          count: 1,
          results: [{ id: 9, last_name: 'Muster', first_name: 'Anna', club_number: '12' }],
        },
      }),
    })
    const user = userEvent.setup()
    aufbau(7)
    await user.click(screen.getByRole('button', { name: /Schnellsuche/ }))
    await user.type(screen.getByRole('combobox', { name: 'Seite oder Mitglied suchen' }), 'Mus')
    const mitglied = await screen.findByRole('option', { name: /Anna Muster/ })
    expect(mitglied).toHaveTextContent('Nr. 12')
    await user.click(mitglied)
    expect(screen.getByTestId('ort')).toHaveTextContent('/mitglieder/9')
  })
})
