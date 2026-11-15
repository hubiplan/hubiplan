import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'

/** Gibt es hier einen Menüpunkt für Untereinheiten? */
export function hasUnitsPage(org: OrgSummary, can: (perm: string) => boolean): boolean {
  if (org.type === 'club') {
    // Vereine ohne Untereinheiten blenden den Menüpunkt aus (Einstellungen › Bezeichnungen)
    if (org.units_in_menu === false) return false
    return can(PERM.settingsView) || can(PERM.rolesView)
  }
  return org.type === 'federation' && can(PERM.clubsManage)
}
