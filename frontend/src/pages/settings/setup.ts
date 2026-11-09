// Einrichtungspunkte aller aktiven Module an einem Ort (Konzept S-02, UX-Audit 08.11.).
// Die Seiten bleiben in ihrem Modul; die Liste kommt aus denselben Quellen wie die
// Seitenleiste (Einstellungen, Mitglieder, Termine, Finanzen), damit neue Einrichtungsseiten
// hier von selbst erscheinen. Den Stand je Punkt liefert der Server (setup-status).
import { PERM } from '../../api/orgs.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { financeAccess, financeSections } from '../finanzen/access.ts'
import { membersVisible, setupTabs } from '../members/access.ts'
import { eventSetupTabs } from '../events/setup.ts'
import { t } from '../../i18n/index.ts'

export interface SetupPoint {
  to: string
  label: string
}

export interface SetupGroup {
  key: string
  label: string
  items: SetupPoint[]
}

/** Gruppen der Übersicht; nur Punkte, deren Seite die Person öffnen darf (W-01). */
export function setupGroups(
  org: OrgSummary,
  settings: { to: string; label: string; setup?: boolean }[],
): SetupGroup[] {
  if (org.type !== 'club' && org.type !== 'federation') return []
  const can = (perm: string) => org.permissions.includes(perm)
  const on = (module: string) => org.modules.includes(module)
  const groups: SetupGroup[] = [
    {
      key: 'verein',
      label: org.type === 'federation' ? t('Dachverband') : t('Verein'),
      items: settings.filter((s) => s.setup).map(({ to, label }) => ({ to, label })),
    },
  ]
  if (can(PERM.membersView) && (membersVisible(org) || org.type === 'federation')) {
    groups.push({ key: 'mitglieder', label: t('Mitglieder'), items: setupTabs(org) })
  }
  if (on('events') && can(PERM.eventsManage)) {
    groups.push({ key: 'termine', label: t('Termine'), items: eventSetupTabs(true, true) })
  }
  const finance = financeSections(financeAccess(org)).filter((i) => i.group?.key === 'einrichten')
  if (finance.length > 0) {
    groups.push({
      key: 'finanzen',
      label: t('Finanzen'),
      items: finance.map(({ to, label }) => ({ to, label })),
    })
  }
  if (on('competitions') && can(PERM.competitionsManage)) {
    groups.push({
      key: 'wettbewerbe',
      label: t('Wettbewerbe'),
      items: [{ to: '/wettbewerbe/einrichtung', label: t('Schießstände') }],
    })
  }
  if (on('music') && can(PERM.musicView)) {
    groups.push({
      key: 'musik',
      label: t('Musik'),
      items: [{ to: '/musik/vorlagen', label: t('Besetzungsvorlagen') }],
    })
  }
  return groups.filter((g) => g.items.length > 0)
}
