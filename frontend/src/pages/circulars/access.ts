// Wer sieht den Menüpunkt „Rundschreiben“ und wer darf verfassen?
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import type { DeptSummary } from '../../api/portal.ts'

/** Darf die Rolle in der Organisation Rundschreiben verfassen? */
export function canWriteCirculars(org: OrgSummary | null): boolean {
  if (!org || !org.permissions.includes(PERM.circularsSend)) return false
  return org.type === 'federation' || org.type === 'club'
}

/** Reiter „Empfangen“: nur ein Verein mit Dachverband bekommt dessen Rundschreiben. */
export function receivesCirculars(org: OrgSummary | null): boolean {
  // ältere Server ohne Angabe: wie bisher jeder Verein
  return !!org && org.type === 'club' && org.has_federation !== false
}

/** Menüpunkt „Rundschreiben“: verfassen oder empfangen */
export function circularsVisible(org: OrgSummary | null, dept: DeptSummary | null): boolean {
  if (org) {
    return (
      canWriteCirculars(org) ||
      (org.permissions.includes(PERM.circularsView) && receivesCirculars(org))
    )
  }
  return !!dept && dept.permissions.includes(PERM.circularsView)
}
