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
  /** Gruppenseite mit Beschreibung der Einträge (S-01 F2) */
  to?: string
  /** Kurzbeschreibung auf der Gruppenseite und der Übersicht */
  text?: string
}

export interface NavItem {
  to: string
  label: string
  group?: NavGroup
  /** Kurzbeschreibung auf der Gruppenseite */
  text?: string
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
    billing: {
      key: 'abrechnen',
      label: t('Beiträge & Rechnungen'),
      to: '/finanzen/abrechnen',
      text: t('Beiträge abrechnen, Rechnungen schreiben und mahnen, eingehende Rechnungen prüfen.'),
    },
    payments: {
      key: 'zahlungen',
      label: t('Zahlungen'),
      to: '/finanzen/zahlungen',
      text: t('Lastschriften einziehen, Kontoauszüge abgleichen und Auszahlungen bündeln.'),
    },
    booking: {
      key: 'buchen',
      label: t('Buchen'),
      to: '/finanzen/buchen',
      text: t('Einnahmen und Ausgaben erfassen, Kasse zählen, Rücklagen und Anlagen führen.'),
    },
    closing: {
      key: 'abschliessen',
      label: t('Auswerten & abschließen'),
      to: '/finanzen/abschliessen',
      text: t('Zahlen auswerten, Steuern prüfen, Zuwendungen bestätigen und das Jahr abschließen.'),
    },
    setup: {
      key: 'einrichten',
      label: t('Einrichten'),
      to: '/finanzen/einrichtung',
      text: t('Grundlagen festlegen: Beitragssätze, Mahnstufen, Konten, Kategorien und Partner.'),
    },
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
      a.billing && {
        to: '/finanzen/rechnungen',
        label: t('Rechnungen'),
        text: t('Alle Rechnungen an Mitglieder und Geschäftspartner'),
      },
      a.billing && {
        to: '/finanzen/rechnungen/leistungen',
        label: t('Leistungsrechnungen'),
        text: t('Rechnungen für Leistungen, auch als E-Rechnung'),
      },
      a.feeRuns && {
        to: '/finanzen/rechnungen/beitragslaeufe',
        label: t('Beitragsläufe'),
        text: t('Beiträge eines Jahres auf einmal abrechnen'),
      },
      a.billing && {
        to: '/finanzen/rechnungen/mahnungen',
        label: t('Mahnungen'),
        text: t('Überfällige Rechnungen anmahnen'),
      },
      a.received && {
        to: '/finanzen/rechnungen/dachverband',
        label: a.receivedLabel,
        text: t('Rechnungen der übergeordneten Einheit an euch'),
      },
      a.finance && {
        to: '/finanzen/rechnungen/eingang',
        label: t('Rechnungseingang'),
        text: t('Eingehende Rechnungen prüfen und bezahlen'),
      },
    ]),
    ...items(g.payments, [
      a.sepa && {
        to: '/finanzen/lastschrift',
        label: t('Lastschriften'),
        text: t('Lastschriftläufe und SEPA-Mandate'),
      },
      a.finance && {
        to: '/finanzen/kontoauszuege',
        label: t('Kontoauszüge'),
        text: t('Umsätze einlesen und zuordnen'),
      },
      a.payouts && {
        to: '/finanzen/sammelauszahlungen',
        label: t('Sammelauszahlungen'),
        text: t('Musikerhonorare gesammelt auszahlen'),
      },
    ]),
    ...items(g.booking, [
      a.finance && {
        to: '/finanzen/kassenbuch',
        label: t('Kassenbuch'),
        text: t('Alle Buchungen des Jahres'),
      },
      a.finance && {
        to: '/finanzen/quittungen',
        label: t('Quittungen'),
        text: t('Quittungen ausstellen und nachsehen'),
      },
      a.cashCounts && {
        to: '/finanzen/kassenzaehlung',
        label: t('Kassenzählung'),
        text: t('Bargeld zählen und abgleichen'),
      },
      a.reserves && {
        to: '/finanzen/ruecklagen',
        label: t('Rücklagen'),
        text: t('Rücklagen bilden und auflösen'),
      },
      a.finance && {
        to: '/finanzen/veranstaltungen',
        label: t('Veranstaltungen'),
        text: t('Einnahmen und Ausgaben je Fest'),
      },
      a.tax && {
        to: '/finanzen/anlagen',
        label: t('Anlagen'),
        text: t('Anlagegüter und Abschreibung'),
      },
      a.tax && {
        to: '/finanzen/pauschalen',
        label: t('Pauschalen'),
        text: t('Ehrenamts- und Übungsleiterpauschale'),
      },
    ]),
    ...items(g.closing, [
      a.finance && {
        to: '/finanzen/auswertung',
        label: t('Auswertung'),
        text: t('Ergebnis nach Konten und Kategorien, Vermögen'),
      },
      a.finance && {
        to: '/finanzen/entwicklung',
        label: t('Entwicklung'),
        text: t('Einnahmen und Ausgaben über die Jahre'),
      },
      a.tax && {
        to: '/finanzen/steuern',
        label: t('Steuern'),
        text: t('Freigrenze, Umsatzsteuer und Mittelverwendung'),
      },
      a.donations && {
        to: '/finanzen/zuwendungen',
        label: t('Zuwendungsbestätigungen'),
        text: t('Spendenbescheinigungen ausstellen'),
      },
      a.finance && {
        to: '/finanzen/abschluss',
        label: t('Jahresabschluss'),
        text: t('Kassenbericht, Kassenprüfung und Abschluss'),
      },
    ]),
    ...items(g.setup, [
      a.feeRuns && {
        to: '/finanzen/einrichtung/beitraege',
        label: t('Beitragssätze'),
        text: t('Beiträge je Mitgliedsart'),
      },
      a.billing && {
        to: '/finanzen/einrichtung/mahnstufen',
        label: t('Mahnstufen'),
        text: t('Fristen, Gebühren und Texte der Mahnungen'),
      },
      a.billing && {
        to: '/finanzen/einrichtung/rechnung',
        label: t('Rechnung & Zahlung'),
        text: t('Nummernkreis, Bankverbindung, Gläubiger-ID'),
      },
      a.finance && {
        to: '/finanzen/einrichtung/konten',
        label: t('Konten'),
        text: t('Bankkonten und Barkassen'),
      },
      a.finance && {
        to: '/finanzen/einrichtung/kategorien',
        label: t('Kategorien'),
        text: t('Kategorien und steuerliche Bereiche'),
      },
      a.donations && {
        to: '/finanzen/einrichtung/zuwendungen',
        label: t('Zuwendungen'),
        text: t('Angaben für Zuwendungsbestätigungen'),
      },
    ]),
  ]
}

/** Einträge unter einem Pfad, z. B. alle Seiten unter /finanzen/rechnungen. */
export function sectionsUnder(a: FinanceAccess, path: string): NavItem[] {
  return financeSections(a).filter((i) => i.to === path || i.to.startsWith(`${path}/`))
}

/** Gruppen mit ihren sichtbaren Einträgen, in der Reihenfolge der Seitenleiste. */
export function financeGroupList(a: FinanceAccess): (NavGroup & { items: NavItem[] })[] {
  const out: (NavGroup & { items: NavItem[] })[] = []
  for (const item of financeSections(a)) {
    if (!item.group) continue
    const last = out[out.length - 1]
    if (last?.key === item.group.key) last.items.push(item)
    else out.push({ ...item.group, items: [item] })
  }
  return out
}
