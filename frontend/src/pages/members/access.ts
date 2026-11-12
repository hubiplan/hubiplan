// Mitglieder: Unterpunkte in der Seitenleiste und Reiter der Einrichtung.
// Welche erscheinen, hängt von den Schaltern der Einheit, Freigaben und Rechten ab.
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { t } from '../../i18n/index.ts'

export interface NavItem {
  to: string
  label: string
}

/** Darf die Organisation Mitglieder sehen (Menüpunkt „Mitglieder“)? */
export function membersVisible(org: OrgSummary | null): boolean {
  if (!org || !org.permissions.includes(PERM.membersView)) return false
  if (org.type === 'club') return org.modules.includes('members')
  return org.type === 'federation' && (federationAccess(org) || ownMembers(org))
}

/** Oberste Einheit, die auch selbst Mitglieder führt */
export function ownMembers(org: OrgSummary) {
  return org.type === 'federation' && !!org.direct_members && org.modules.includes('members')
}

/** Dachverband mit Zugriff auf die Mitgliedsdaten der Vereine */
export function federationAccess(org: OrgSummary) {
  return !!org.federation_member_access && org.federation_member_access !== 'none'
}

/** Unterpunkte von Mitglieder (Seitenleiste). */
export function memberSections(org: OrgSummary | null): NavItem[] {
  if (!org || !membersVisible(org)) return []
  if (org.type === 'federation' && !ownMembers(org)) {
    return [
      { to: '/mitglieder', label: t('Mitgliederliste') },
      { to: '/mitglieder/entwicklung', label: t('Entwicklung') },
      { to: '/mitglieder/einrichtung', label: t('Einrichtung') },
    ]
  }
  const canEdit = org.permissions.includes(PERM.membersEdit)
  if (org.type === 'federation') {
    // Eigene Mitglieder; die Übersicht über alle Einheiten darunter daneben
    return [
      { to: '/mitglieder', label: t('Eigene Mitglieder') },
      ...(federationAccess(org)
        ? [{ to: '/mitglieder/verbund', label: t('Alle Mitglieder') }]
        : []),
      { to: '/mitglieder/entwicklung', label: t('Entwicklung') },
      ...(federationAccess(org)
        ? [{ to: '/mitglieder/verbund/entwicklung', label: t('Entwicklung aller') }]
        : []),
      ...extras(org),
      { to: '/mitglieder/aemter', label: t('Ämter') },
      { to: '/mitglieder/einrichtung', label: t('Einrichtung') },
    ]
  }
  return [
    { to: '/mitglieder', label: t('Mitgliederliste') },
    { to: '/mitglieder/antraege', label: t('Mitgliedsanträge') },
    { to: '/mitglieder/haushalte', label: t('Haushalte und Firmen') },
    { to: '/mitglieder/entwicklung', label: t('Entwicklung') },
    ...extras(org),
    { to: '/mitglieder/aemter', label: t('Ämter') },
    { to: '/mitglieder/anfragen', label: t('Änderungen und Wechsel') },
    ...(canEdit ? [{ to: '/mitglieder/import', label: t('Import') }] : []),
    { to: '/mitglieder/einrichtung', label: t('Einrichtung') },
  ]
}

/** Jubiläen (Modul „Ehrungen & Jubiläen“) und Würdenträger (Modul „Würden“) */
function extras(org: OrgSummary): NavItem[] {
  return [
    ...(org.modules.includes('awards')
      ? [{ to: '/mitglieder/jubilaeen', label: t('Jubiläen') }]
      : []),
    ...(org.modules.includes('honors')
      ? [{ to: '/mitglieder/wuerdentraeger', label: t('Würdenträger') }]
      : []),
  ]
}

export function requestTabs(): NavItem[] {
  return [
    { to: '/mitglieder/anfragen', label: t('Wechselanfragen') },
    { to: '/mitglieder/anfragen/aenderungen', label: t('Datenänderungen') },
    { to: '/mitglieder/anfragen/kuendigungen', label: t('Kündigungen') },
  ]
}

export function setupTabs(org: OrgSummary): NavItem[] {
  const club = org.type === 'club'
  const awards = org.modules.includes('awards')
  return [
    ...(club || ownMembers(org)
      ? [{ to: '/mitglieder/einrichtung/mitgliedsarten', label: t('Mitgliedsarten') }]
      : []),
    ...(awards ? [{ to: '/mitglieder/einrichtung/ehrungen', label: t('Ehrungen') }] : []),
    { to: '/mitglieder/einrichtung/zusatzfelder', label: t('Zusatzfelder') },
    ...(club ? [{ to: '/mitglieder/einrichtung/antrag', label: t('Online-Antrag') }] : []),
    ...(awards ? [{ to: '/mitglieder/einrichtung/jubilaeen', label: t('Jubiläen & Dauer') }] : []),
    ...(club
      ? [{ to: '/mitglieder/einrichtung/mitgliederbereich', label: t('Mitgliederbereich & Fotos') }]
      : []),
  ]
}
