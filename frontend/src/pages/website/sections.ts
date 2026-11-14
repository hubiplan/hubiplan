// Webseite: Unterpunkte in der Seitenleiste (wie bei Mitglieder und Finanzen).
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { t } from '../../i18n/index.ts'

export interface NavItem {
  to: string
  label: string
  /** Zwischenüberschrift in der Seitenleiste (Menüprüfung M-09), Reihenfolge unverändert */
  section?: string
}

const content = t('Inhalte')
const design = t('Gestaltung')
const structure = t('Aufbau')
const operation = t('Betrieb')

const ALL: NavItem[] = [
  { to: '/webseite', label: t('Übersicht') },
  { to: '/webseite/startseite', label: t('Startseite'), section: content },
  { to: '/webseite/inhalte', label: t('Texte'), section: content },
  { to: '/webseite/bilder', label: t('Bilder'), section: content },
  { to: '/webseite/galerie', label: t('Galerie'), section: content },
  { to: '/webseite/dokumente', label: t('Dokumente'), section: content },
  { to: '/webseite/beitraege', label: t('Social Media'), section: content },
  // S1/S3 (Ralf 14.11.2026): Gestaltung in eigenen Punkten, jeder mit Vorschau
  { to: '/webseite/gestaltung', label: t('Design und Farben'), section: design },
  { to: '/webseite/feinabstimmung', label: t('Feinabstimmung'), section: design },
  { to: '/webseite/bereiche', label: t('Bereiche'), section: design },
  { to: '/webseite/fassungen', label: t('Fassungen'), section: design },
  { to: '/webseite/aufbau', label: t('Menü und Bausteine'), section: structure },
  { to: '/webseite/kontakt', label: t('Kontaktformular'), section: operation },
  { to: '/webseite/domain', label: t('Internetadresse'), section: operation },
]

/** Verwalter sehen alles. Wer nur Inhalte pflegt, sieht nur „Startseite“ (Inhalte der Abschnitte), „Texte“, „Bilder“, „Galerie“, „Dokumente“ und „Social Media“. */
export function websiteSections(org: OrgSummary | null): NavItem[] {
  if (!org) return []
  // Social Media ist ein eigenes Modul
  const all = org.modules.includes('social')
    ? ALL
    : ALL.filter((s) => s.to !== '/webseite/beitraege')
  // S2 (Ralf 14.11.2026): eine Startseite für alle; Verwalter stellen dort auch zusammen
  if (org.permissions.includes(PERM.websiteManage)) return all
  if (org.permissions.includes(PERM.websiteContent)) {
    return all.filter((s) =>
      [
        '/webseite/startseite',
        '/webseite/inhalte',
        '/webseite/bilder',
        '/webseite/galerie',
        '/webseite/dokumente',
        '/webseite/beitraege',
      ].includes(s.to),
    )
  }
  return []
}
