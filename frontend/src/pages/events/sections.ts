// Unterpunkte von Termine im Menü (Kalender, Kalender-Abo, Einrichtung).
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { DEPT_PERM } from '../../api/portal.ts'
import type { DeptSummary, PortalEntry } from '../../api/portal.ts'
import { t } from '../../i18n/index.ts'
import { eventSetupTabs } from './setup.ts'
import type { EventSetupTab } from './setup.ts'

export interface EventAccess {
  manage: boolean
  categories: boolean
  isPortal: boolean
}

/** Welchen Kalender die Seite zeigt: Verein vor Untereinheit vor Mitgliederbereich. */
export function eventAccess(
  org: OrgSummary | null,
  dept: DeptSummary | null,
  portal: PortalEntry | null,
): EventAccess | null {
  if (org && (org.type === 'club' || org.type === 'federation')) {
    const manage = org.permissions.includes(PERM.eventsManage)
    return { manage, categories: manage, isPortal: false }
  }
  if (dept) {
    return {
      manage: dept.permissions.includes(DEPT_PERM.eventsManage),
      categories: false,
      isPortal: false,
    }
  }
  if (portal) return { manage: false, categories: false, isPortal: true }
  return null
}

/**
 * Unterpunkte von Termine: Kalender, im Mitgliederbereich das Kalender-Abo und zuletzt die
 * Einrichtung. Sie stehen wie bei den anderen Modulen im Menü; im Inhalt bleibt nur eine
 * Reiterzeile, die der Einrichtung (Ralf 22.11.: nicht zwei Reiterzeilen übereinander).
 */
export function eventSections(access: EventAccess | null): EventSetupTab[] {
  if (!access) return []
  const setup = eventSetupTabs(access.manage, access.categories)
  return [
    { to: '/termine', label: t('Kalender') },
    ...(access.isPortal ? [{ to: '/termine/abo', label: t('Kalender-Abo') }] : []),
    ...(setup.length > 0 ? [{ to: '/termine/einrichtung', label: t('Einrichtung') }] : []),
  ]
}
