// UX-Audit 16.11.2026, VW-21: Listen als einfache Tabelle bekommen ab mehr als 20 Zeilen ein
// Suchfeld (useRowSearch). Neue Tabellen nutzen DataTable, die serverseitige Suche oder
// useRowSearch; wer bewusst darauf verzichtet, trägt die Datei unten ein.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { useRowSearch } from '../components/RowSearch.tsx'

/**
 * Tabellen ohne Suche, Stand 17.11.2026: Auswertungen und Summen (Finanzen), Eingabetabellen,
 * Ergebnislisten eines Wettbewerbs und Listen, die von Natur aus kurz sind (Arten, Stufen,
 * Vorlagen). Die Liste darf kürzer werden, aber nicht länger.
 */
const WITHOUT_SEARCH = [
  'components/DataTransfer.tsx',
  'components/RoleEditor.tsx',
  'components/TodoRemote.tsx',
  'components/UnitRoles.tsx',
  'components/calendar/Rsvp.tsx',
  'components/charts/Charts.tsx',
  'components/circulars/CircularsArea.tsx',
  'components/circulars/MailingListsArea.tsx',
  'learning/Aids.tsx',
  'pages/TodosPage.tsx',
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
  'pages/entries/EntryResults.tsx',
  'pages/events/EventsPage.tsx',
  'pages/expenses/ExpensesPage.tsx',
  'pages/finance/CashCountsPage.tsx',
  'pages/finance/CashReceiptsPage.tsx',
  'pages/finance/ClosingsPage.tsx',
  'pages/finance/MasterDataPages.tsx',
  'pages/finance/ReservesPage.tsx',
  'pages/finance/SplitEditor.tsx',
  'pages/finanzen/AllowancesPage.tsx',
  'pages/finanzen/ArtistFeesPage.tsx',
  'pages/finanzen/AssetsPage.tsx',
  'pages/finanzen/AuditPage.tsx',
  'pages/finanzen/BudgetPage.tsx',
  'pages/finanzen/NetAssetsPage.tsx',
  'pages/finanzen/OverviewPages.tsx',
  'pages/finanzen/TaxPage.tsx',
  'pages/finanzen/UseOfFundsPage.tsx',
  'pages/finanzen/VatPage.tsx',
  'pages/helpers/HelpersPage.tsx',
  'pages/members/ApplicationsPage.tsx',
  'pages/members/FeeProofsPage.tsx',
  'pages/members/FeesTab.tsx',
  'pages/members/FieldsTab.tsx',
  'pages/members/JubileesPage.tsx',
  'pages/members/MemberFilePage.tsx',
  'pages/members/PublicationSection.tsx',
  'pages/music/ProgramPanel.tsx',
  'pages/platform/PlatformPages.tsx',
  'pages/portal/PortalHelpers.tsx',
  'pages/portal/PortalPage.tsx',
  'pages/settings/FieldsPage.tsx',
  'pages/settings/MemberTypesPage.tsx',
  'pages/settings/NextcloudPage.tsx',
  'pages/settings/PeeringPage.tsx',
  'pages/settings/RolesPage.tsx',
  'pages/surveys/SurveyParts.tsx',
  'pages/surveys/SurveysPage.tsx',
]

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name)
    if (e.isDirectory()) return e.name === 'test' ? [] : sources(path)
    return e.name.endsWith('.tsx') ? [path] : []
  })
}

const CONTROLS =
  /ListControls|PageNav|DataTable|type="search"|SearchInput|usePaged|page_size|\bpage=|useRowSearch/

function List({ names }: { names: string[] }) {
  const search = useRowSearch(names, (n) => n, 'Konten')
  return (
    <div>
      {search.field}
      <ul>
        {search.shown.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </div>
  )
}

describe('VW-21 Tabellen', () => {
  it('zeigt bei kurzen Listen kein Suchfeld', () => {
    render(<List names={['Erika Muster', 'Max Beispiel']} />)
    expect(screen.queryByRole('searchbox')).toBeNull()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('filtert lange Listen nach allen Suchwörtern, ohne auf Groß- und Kleinschreibung zu achten', async () => {
    const user = userEvent.setup()
    const names = Array.from({ length: 30 }, (_, i) => `Person ${i + 1} Muster`)
    names.push('Jörg Beispiel')
    render(<List names={names} />)
    const field = screen.getByRole('searchbox', { name: 'Konten durchsuchen' })
    expect(screen.getAllByRole('listitem')).toHaveLength(31)
    await user.type(field, 'beispiel JORG')
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText('1 von 31 Einträgen')).toBeTruthy()
  })

  it('lässt keine neue Tabelle ohne Suche, Seiten oder Begründung zu', () => {
    const without = sources('src')
      .filter((f) => {
        const text = readFileSync(f, 'utf8')
        return text.includes('<table') && !CONTROLS.test(text)
      })
      .map((f) => f.replace(/\\/g, '/').replace(/^src\//, ''))
      .sort()
    expect(without.filter((f) => !WITHOUT_SEARCH.includes(f))).toEqual([])
  })
})
