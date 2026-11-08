// Finanzen: Kasse (finance) und Beiträge/Rechnungen (billing) unter einem
// Menüpunkt. Welche Unterpunkte erscheinen, hängt von Modulen und Rechten ab.
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { DEFAULT_TERMS } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'

export interface FinanceAccess {
  /** Kasse: Kassenbuch, Konten, Kategorien, Abschluss */
  finance: boolean
  financeEdit: boolean
  /** Beiträge und Rechnungen, Mahnungen, Lastschriften */
  billing: boolean
  billingEdit: boolean
  /** Beitragsläufe und Beitragssätze (nicht im Arbeitsbereich einer Untereinheit) */
  feeRuns: boolean
  /** SEPA-Lastschrift eingeschaltet: Lastschriftläufe und Mandate */
  sepa: boolean
  /** Rechnungen des Dachverbands an den Verein */
  received: boolean
  /** Name des Dachverbands mit Präposition, z. B. „Vom BSV“ */
  receivedLabel: string
  /** Zuwendungsbestätigungen: Modul „donations“ und Kasse */
  donations: boolean
  /** Zählprotokoll und Kassenbericht für Feste (zuschaltbar) */
  cashCounts: boolean
  /** Rücklagen nach § 62 AO (zuschaltbar) */
  reserves: boolean
  /** Steuerliche Auswertung: Modul „Steuern & Gemeinnützigkeit“ und Kasse */
  tax: boolean
  /** Sammelauszahlungen aus der Musikerabrechnung (Modul Musik, Termine lesen) */
  payouts: boolean
}

export function financeAccess(org: OrgSummary | null): FinanceAccess {
  const none = {
    finance: false,
    financeEdit: false,
    billing: false,
    billingEdit: false,
    feeRuns: false,
    sepa: false,
    received: false,
    receivedLabel: '',
    donations: false,
    cashCounts: false,
    reserves: false,
    tax: false,
    payouts: false,
  }
  if (!org || org.type === 'platform') return none
  const has = (p: string) => org.permissions.includes(p)
  const finance = org.modules.includes('finance') && has(PERM.financeView)
  const billing = org.modules.includes('billing') && has(PERM.billingView)
  return {
    finance,
    financeEdit: finance && has(PERM.financeEdit),
    billing,
    billingEdit: billing && has(PERM.billingEdit),
    feeRuns: billing && org.type !== 'unit',
    sepa: billing && org.type !== 'unit' && !!org.sepa_enabled,
    received: org.type === 'club' && !!org.parent_name && (finance || billing),
    receivedLabel:
      (org.department_terms ?? DEFAULT_TERMS).dv_Vom ?? t('Von der übergeordneten Einheit'),
    // Modul „Zuwendungsbestätigungen“; ausgestellt wird erst mit Schalter und gültigem Bescheid
    donations: finance && org.modules.includes('donations'),
    cashCounts: finance && !!org.cash_counts_enabled,
    reserves: finance && !!org.reserves_enabled,
    tax: finance && org.modules.includes('tax'),
    payouts: finance && org.modules.includes('music') && has(PERM.eventsView),
  }
}

/** Arbeitsgruppe in der Seitenleiste (Konzept S-01): aufklappbar, eine offen. */
export interface NavGroup {
  key: string
  label: string
}

export interface NavItem {
  to: string
  label: string
  group?: NavGroup
}

/**
 * Arbeitsgruppen von Finanzen nach dem Jahreslauf (Konzept S-01, UX-Audit 08.11. W-03).
 * Reihenfolge = Reihenfolge in der Seitenleiste.
 */
export function financeGroups(): Record<
  'billing' | 'payments' | 'booking' | 'closing' | 'setup',
  NavGroup
> {
  return {
    billing: { key: 'abrechnen', label: t('Beiträge & Rechnungen') },
    payments: { key: 'zahlungen', label: t('Zahlungen') },
    booking: { key: 'buchen', label: t('Buchen') },
    closing: { key: 'abschliessen', label: t('Auswerten & abschließen') },
    setup: { key: 'einrichten', label: t('Einrichten') },
  }
}

/**
 * Unterpunkte von Finanzen (Seitenleiste), je mit ihrer Arbeitsgruppe. Es gibt keine
 * dritte Ebene mehr für Rechnungen und Einrichtung: deren frühere Reiter sind Einträge
 * ihrer Gruppe, die Adressen bleiben gleich.
 */
export function financeSections(a: FinanceAccess): NavItem[] {
  if (!a.finance && !a.billing) return []
  const g = financeGroups()
  const items = (group: NavGroup, list: (NavItem | false)[]): NavItem[] =>
    list.filter((i): i is NavItem => !!i).map((i) => ({ ...i, group }))
  return [
    { to: '/finanzen', label: t('Übersicht') },
    ...items(g.billing, [
      a.billing && { to: '/finanzen/rechnungen', label: t('Rechnungen') },
      a.billing && { to: '/finanzen/rechnungen/leistungen', label: t('Leistungsrechnungen') },
      a.feeRuns && { to: '/finanzen/rechnungen/beitragslaeufe', label: t('Beitragsläufe') },
      a.billing && { to: '/finanzen/rechnungen/mahnungen', label: t('Mahnungen') },
      a.received && { to: '/finanzen/rechnungen/dachverband', label: a.receivedLabel },
      a.finance && { to: '/finanzen/rechnungen/eingang', label: t('Rechnungseingang') },
    ]),
    ...items(g.payments, [
      a.sepa && { to: '/finanzen/lastschrift', label: t('Lastschriften') },
      a.finance && { to: '/finanzen/kontoauszuege', label: t('Kontoauszüge') },
      a.payouts && { to: '/finanzen/sammelauszahlungen', label: t('Sammelauszahlungen') },
    ]),
    ...items(g.booking, [
      a.finance && { to: '/finanzen/kassenbuch', label: t('Kassenbuch') },
      a.finance && { to: '/finanzen/quittungen', label: t('Quittungen') },
      a.cashCounts && { to: '/finanzen/kassenzaehlung', label: t('Kassenzählung') },
      a.reserves && { to: '/finanzen/ruecklagen', label: t('Rücklagen') },
      a.finance && { to: '/finanzen/veranstaltungen', label: t('Veranstaltungen') },
      a.tax && { to: '/finanzen/anlagen', label: t('Anlagen') },
      a.tax && { to: '/finanzen/pauschalen', label: t('Pauschalen') },
    ]),
    ...items(g.closing, [
      a.finance && { to: '/finanzen/auswertung', label: t('Auswertung') },
      a.finance && { to: '/finanzen/entwicklung', label: t('Entwicklung') },
      a.tax && { to: '/finanzen/steuern', label: t('Steuern') },
      a.donations && { to: '/finanzen/zuwendungen', label: t('Zuwendungsbestätigungen') },
      a.finance && { to: '/finanzen/abschluss', label: t('Jahresabschluss') },
    ]),
    ...items(g.setup, [
      a.feeRuns && { to: '/finanzen/einrichtung/beitraege', label: t('Beitragssätze') },
      a.billing && { to: '/finanzen/einrichtung/mahnstufen', label: t('Mahnstufen') },
      a.billing && { to: '/finanzen/einrichtung/rechnung', label: t('Rechnung & Zahlung') },
      a.finance && { to: '/finanzen/einrichtung/konten', label: t('Konten') },
      a.finance && { to: '/finanzen/einrichtung/kategorien', label: t('Kategorien') },
      a.donations && { to: '/finanzen/einrichtung/zuwendungen', label: t('Zuwendungen') },
      // Geschäftspartner gelten für Ein- und Ausgang, deshalb bei „Einrichten“ (Menüprüfung M-10)
      { to: '/finanzen/geschaeftspartner', label: t('Geschäftspartner') },
    ]),
  ]
}

/** Einträge unter einem Pfad, z. B. alle Seiten unter /finanzen/rechnungen. */
export function sectionsUnder(a: FinanceAccess, path: string): NavItem[] {
  return financeSections(a).filter((i) => i.to === path || i.to.startsWith(`${path}/`))
}
