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
const structure = t('Aufbau')
const operation = t('Betrieb')

const ALL: NavItem[] = [
  { to: '/webseite', label: t('Übersicht') },
  { to: '/webseite/inhalte', label: t('Texte'), section: content },
  { to: '/webseite/bilder', label: t('Bilder'), section: content },
  { to: '/webseite/galerie', label: t('Galerie'), section: content },
  { to: '/webseite/dokumente', label: t('Dokumente'), section: content },
  { to: '/webseite/beitraege', label: t('Social Media'), section: content },
  { to: '/webseite/aufbau', label: t('Menü und Bereiche'), section: structure },
  { to: '/webseite/gestaltung', label: t('Gestaltung'), section: structure },
  { to: '/webseite/kontakt', label: t('Kontaktformular'), section: operation },
  { to: '/webseite/domain', label: t('Internetadresse'), section: operation },
]

/** Wer nur Inhalte pflegt, sieht nur „Texte“, „Bilder“, „Galerie“, „Dokumente“ und „Social Media“. */
export function websiteSections(org: OrgSummary | null): NavItem[] {
  if (!org) return []
  // Social Media ist ein eigenes Modul
  const all = org.modules.includes('social')
    ? ALL
    : ALL.filter((s) => s.to !== '/webseite/beitraege')
  if (org.permissions.includes(PERM.websiteManage)) return all
  if (org.permissions.includes(PERM.websiteContent)) {
    return all.filter((s) =>
      [
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

/** Überschrift zum aktuellen Pfad */
export function sectionTitle(pathname: string): string {
  const path = pathname.replace(/\/+$/, '') || '/webseite'
  return ALL.find((s) => s.to === path)?.label ?? t('Webseite')
}
