// UX-Audit 16.11.2026, VW-22: Bearbeitungsformulare speichern automatisch (useAutoSave mit
// SaveStatus und „Schließen“). Einen Knopf „Speichern“ behält nur, was folgenreich ist, einen
// Zeitraum festlegt, etwas neu anlegt oder ein kleiner Dialog ist. Regel: docs/rueckgaengig.md.
// Wer einen neuen Knopf „Speichern“ braucht, trägt die Datei hier mit Begründung ein.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Dateien mit Knopf „Speichern“, Stand 18.11.2026. Die Liste darf kürzer werden, nicht länger. */
const WITH_BUTTON: Record<string, string> = {
  // Rechte und Zugang
  'components/RoleEditor.tsx': 'Rollen und Rechte',
  'pages/settings/RolesPage.tsx': 'Rollen und Rechte',
  'pages/settings/NextcloudPage.tsx': 'Zugang: wer sich anmelden darf, Dienstkonto, Sperren',
  'pages/settings/PasskeyCard.tsx': 'kleiner Dialog (Name des Passkeys)',
  'pages/platform/PlatformPages.tsx': 'Plattform: wäre schon beim Tippen wirksam',
  // Mitgliedsakte: Zeiträume und Abrechnung
  'pages/members/MemberFilePage.tsx': 'Zeiträume von Mitgliedschaft und Abteilung',
  'pages/members/HonoraryAwards.tsx': 'Zeitraum einer Verleihung, erscheint auf der Webseite',
  'pages/members/QualificationsCard.tsx': 'Gültigkeit einer Qualifikation',
  'pages/members/FeeProofsCard.tsx': 'Ende einer Ermäßigung, wirkt auf den Beitrag',
  'pages/members/HouseholdPayer.tsx': 'Zahler, wirkt auf Rechnungen',
  'pages/members/BillingAddressSection.tsx': 'nur beim ersten Festlegen (Neuanlage)',
  'pages/members/ContactPersons.tsx': 'nur beim Hinzufügen (Neuanlage)',
  'pages/members/HouseholdsPage.tsx': 'Haushalt, wirkt auf Rechnungen',
  'pages/members/QualificationTypesPage.tsx': 'Arten mit Fristen und Erinnerungen',
  // Finanzen: bewusst mit Knopf
  'pages/billing/DebitsPage.tsx': 'SEPA-Mandat',
  'pages/billing/FeeProofDiscounts.tsx': 'Ermäßigungen, wirken auf Beiträge',
  'pages/billing/HouseholdFeeRules.tsx': 'Beitragsregeln für Haushalte',
  'pages/expenses/ExpensesPage.tsx': 'Einstellungen der Auslagen (Freigabe, Konten)',
  'pages/finance/CashReceiptsPage.tsx': 'Barbeleg',
  'pages/finance/DonationsPage.tsx': 'Spenden und Bescheinigungen',
  'pages/finance/ProjectsPage.tsx': 'kleiner Dialog (Name)',
  'pages/finanzen/AssetsPage.tsx': 'Anlagegut mit Abschreibung',
  'pages/finanzen/AuditPage.tsx': 'Kassenprüfung',
  'pages/finanzen/BudgetPage.tsx': 'Planwerte',
  'pages/portal/PortalExpenses.tsx': 'Auslage einreichen',
  // Wettbewerbe, Belegung, Ausstattung, Proben (docs/rueckgaengig.md)
  'pages/bookings/BookingsPage.tsx': 'Belegungen (Serien, Überschneidungen)',
  'pages/competitions/BirdStand.tsx': 'Wertung',
  'pages/competitions/History.tsx': 'Wertung',
  'pages/competitions/StandPanel.tsx': 'Wertung',
  'pages/materials/MaterialsPage.tsx': 'Neuanlage',
  'pages/music/AvailabilityPage.tsx': 'Rückmeldung der Verfügbarkeit',
  'pages/music/EnsembleTemplatesPage.tsx': 'Neuanlage',
  'pages/music/EquipmentPage.tsx': 'Ausgabe, Rückgabe, Wartung',
  'pages/music/MusicPage.tsx': 'Neuanlage',
  'pages/music/RehearsalProgramEditor.tsx': 'Probenprogramm (Termin oder Serie)',
  'pages/music/ScoreFoldersPanel.tsx': 'Neuanlage',
  'pages/music/ScoresPage.tsx': 'Neuanlage',
  'pages/music/SettlementPanel.tsx': 'Abrechnung eines Auftritts',
  // Sonstiges
  'components/calendar/Registration.tsx': 'Anmeldung mit Preisen und Rechnungen einrichten',
  'help/HelpExtras.tsx': 'eigene Notiz zur Hilfe',
  'pages/PublicRsvpPage.tsx': 'öffentliche Rückmeldung zu einem Termin',
  'pages/obligations/ObligationsPage.tsx': 'Frist mit Erinnerungen',
  'pages/portal/PortalPage.tsx': 'Mitgliederbereich (Änderungsmeldung an den Vorstand)',
  'pages/surveys/SurveysPage.tsx': 'Umfrage (Fragen ändern laufende Antworten)',
  'pages/website/DocumentsPage.tsx': 'öffentliches Dokument',
  'pages/website/GalleryPage.tsx': 'öffentliche Galerie',
}

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name)
    if (e.isDirectory()) return e.name === 'test' ? [] : sources(path)
    return e.name.endsWith('.tsx') ? [path] : []
  })
}

const BUTTON = /t\('Speichern'\)|tc\('[a-z]+\|Speichern'\)/

describe('VW-22 Speichern', () => {
  const root = join(process.cwd(), 'src')
  const found = sources(root)
    .filter((path) => BUTTON.test(readFileSync(path, 'utf8')))
    .map((path) => path.slice(root.length + 1).replaceAll('\\', '/'))
    .sort()

  it('ein Knopf „Speichern“ steht nur in begründeten Formularen', () => {
    expect(found.filter((file) => !(file in WITH_BUTTON))).toEqual([])
  })

  it('die Liste der Ausnahmen nennt nur Dateien, die den Knopf noch haben', () => {
    expect(Object.keys(WITH_BUTTON).filter((file) => !found.includes(file))).toEqual([])
  })

  it('Orte speichern beim Bearbeiten automatisch', () => {
    const places = readFileSync(join(root, 'pages/settings/PlacesPage.tsx'), 'utf8')
    expect(places).toMatch(/useAutoSave\(/)
    expect(places).toMatch(/<SaveStatus auto=\{auto\} \/>/)
  })
})
