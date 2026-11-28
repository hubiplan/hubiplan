// UX-Audit 16.11.2026, VW-21: Listen als einfache Tabelle lassen sich nach Spalten sortieren
// (useRowSort, dieselben Spaltenköpfe wie DataTable). Wer eine Tabelle bewusst ohne Sortieren
// lässt, trägt die Datei unten ein.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { useRowSort } from '../components/RowSort.tsx'

/**
 * Tabellen ohne Sortieren, Stand 19.11.2026: Summen und Auswertungen, Eingabe- und
 * Auswahltabellen, feste Abläufe (Ergebnisse, Schichten, Belegungsplan) und kurze Listen.
 * Die Liste darf kürzer werden, aber nicht länger.
 */
const WITHOUT_SORT = [
  'components/DataTransfer.tsx',
  'components/RoleEditor.tsx',
  'components/TodoRemote.tsx',
  'components/UnitRoles.tsx',
  'components/calendar/Rsvp.tsx',
  'components/charts/Charts.tsx',
  'components/circulars/CircularsArea.tsx',
  'components/circulars/MailingListsArea.tsx',
  'components/circulars/RecipientPanel.tsx',
  'learning/Aids.tsx',
  'pages/TodosPage.tsx',
  'pages/billing/DebitsPage.tsx',
  'pages/billing/DunningsPage.tsx',
  'pages/billing/FeeProofDiscounts.tsx',
  'pages/billing/MyInvoices.tsx',
  'pages/billing/RulesPage.tsx',
  'pages/bookings/BookingsPage.tsx',
  'pages/competitions/BirdSetup.tsx',
  'pages/competitions/ForeignPanel.tsx',
  'pages/competitions/LiveTables.tsx',
  'pages/competitions/MemberTab.tsx',
  'pages/competitions/ResultsPanel.tsx',
  'pages/competitions/Shootoffs.tsx',
  // Keine neuen Tabellen: Meldereihenfolge und Fassungen einer Meldung standen bisher in
  // EntriesPage.tsx und fielen dort nicht auf, weil die Datei auch die Ausschreibungsliste
  // mit Suche und Sortierung enthielt. Beide haben eine feste Reihenfolge.
  'pages/entries/EntryBlocks.tsx',
  'pages/entries/EntryResults.tsx',
  'pages/entries/EntrySubmit.tsx',
  'pages/events/EventsPage.tsx',
  'pages/finance/BankAccess.tsx',
  'pages/finance/CashCountsPage.tsx',
  'pages/finance/ClosingsPage.tsx',
  'pages/finance/MasterDataPages.tsx',
  'pages/finance/ProjectsPage.tsx',
  'pages/finance/ReservesPage.tsx',
  'pages/finance/SplitEditor.tsx',
  'pages/finanzen/AllowancesPage.tsx',
  'pages/finanzen/ArtistFeesPage.tsx',
  'pages/finanzen/AuditPage.tsx',
  'pages/finanzen/BudgetPage.tsx',
  'pages/finanzen/NetAssetsPage.tsx',
  'pages/finanzen/OverviewPages.tsx',
  'pages/finanzen/TaxPage.tsx',
  'pages/finanzen/UseOfFundsPage.tsx',
  'pages/finanzen/VatPage.tsx',
  'pages/meetings/MeetingsPage.tsx',
  'pages/meetings/ResolutionBook.tsx',
  // Stichtagsstatistik: feste Zeilen (Altersgruppen, Summen), Reihenfolge ist Teil der Meldung
  'pages/members/CensusPage.tsx',
  'pages/members/FeesTab.tsx',
  'pages/members/FieldsTab.tsx',
  'pages/members/JubileesPage.tsx',
  'pages/members/MemberFilePage.tsx',
  'pages/members/PublicationSection.tsx',
  // Auftritte je Jahr und Art: Jahre als Spalten, Arten alphabetisch; kleine Zähltabelle
  'pages/music/MusicPage.tsx',
  'pages/music/ProgramPanel.tsx',
  'pages/partners/PartnersPage.tsx',
  'pages/platform/PlatformPages.tsx',
  'pages/portal/PortalHelpers.tsx',
  'pages/portal/PortalPage.tsx',
  'pages/settings/FieldsPage.tsx',
  'pages/settings/MemberTypesPage.tsx',
  'pages/settings/NextcloudPage.tsx',
  'pages/settings/PeeringPage.tsx',
  'pages/settings/RolesPage.tsx',
  'pages/surveys/SurveyParts.tsx',
]

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name)
    if (e.isDirectory()) return e.name === 'test' ? [] : sources(path)
    return e.name.endsWith('.tsx') ? [path] : []
  })
}

const SORTING = /DataTable|useRowSort|ListControls|sort=|ordering/

type Row = { name: string; amount: number | null }

function Table({ rows }: { rows: Row[] }) {
  const sorting = useRowSort(rows, { name: (r) => r.name, amount: (r) => r.amount })
  return (
    <table>
      <thead>
        <tr>
          {sorting.head('name', 'Name')}
          {sorting.head('amount', 'Betrag')}
        </tr>
      </thead>
      <tbody>
        {sorting.rows.map((r) => (
          <tr key={r.name}>
            <td>{r.name}</td>
            <td>{r.amount ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const names = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[0].textContent)

describe('VW-21 Sortieren in einfachen Tabellen', () => {
  it('sortiert auf Klick auf- und absteigend, Zahlen im Text natürlich, leere Werte zuletzt', async () => {
    const user = userEvent.setup()
    render(
      <Table
        rows={[
          { name: 'Zug 10', amount: 5 },
          { name: 'Zug 2', amount: null },
          { name: 'Ärzte', amount: 20 },
        ]}
      />,
    )
    expect(names()).toEqual(['Zug 10', 'Zug 2', 'Ärzte'])
    const name = screen.getByRole('button', { name: /Name/ })
    await user.click(name)
    expect(names()).toEqual(['Ärzte', 'Zug 2', 'Zug 10'])
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute(
      'aria-sort',
      'ascending',
    )
    await user.click(name)
    expect(names()).toEqual(['Zug 10', 'Zug 2', 'Ärzte'])
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    await user.click(screen.getByRole('button', { name: /Betrag/ }))
    expect(names()).toEqual(['Zug 10', 'Ärzte', 'Zug 2'])
    expect(screen.getByRole('columnheader', { name: /Name/ })).not.toHaveAttribute('aria-sort')
  })

  it('jede Liste mit Suchfeld lässt sich auch sortieren', () => {
    const missing = sources('src')
      .filter((f) => {
        const text = readFileSync(f, 'utf8')
        return text.includes('useRowSearch(') && !text.includes('useRowSort(')
      })
      .map((f) => f.replace(/\\/g, '/'))
    expect(missing).toEqual([])
  })

  it('lässt keine neue Tabelle ohne Sortieren oder Begründung zu', () => {
    const without = sources('src')
      .filter((f) => {
        const text = readFileSync(f, 'utf8')
        return text.includes('<table') && !SORTING.test(text)
      })
      .map((f) => f.replace(/\\/g, '/').replace(/^src\//, ''))
      .sort()
    expect(without.filter((f) => !WITHOUT_SORT.includes(f))).toEqual([])
  })
})
