// Unterpunkte des Arbeitsbereichs einer Untereinheit in der Seitenleiste, wie bei allen
// anderen Bereichen (Menüprüfung 2, N-07; UX-Audit W09).
import { DEPT_PERM } from '../../api/portal.ts'
import type { DeptSummary } from '../../api/portal.ts'
import { t } from '../../i18n/index.ts'

export function departmentSections(dept: DeptSummary | null): { to: string; label: string }[] {
  if (!dept) return []
  const can = (p: string) => dept.permissions.includes(p)
  return [
    ...(can(DEPT_PERM.membersView) || !can(DEPT_PERM.invoicesView)
      ? [{ to: '/abteilung', label: t('Mitglieder') }]
      : []),
    ...(can(DEPT_PERM.membersView)
      ? [{ to: '/abteilung/entwicklung', label: t('Entwicklung') }]
      : []),
    ...(can(DEPT_PERM.invoicesView)
      ? [
          {
            to: can(DEPT_PERM.membersView) ? '/abteilung/rechnungen' : '/abteilung',
            label: t('Rechnungen'),
          },
        ]
      : []),
    ...(can(DEPT_PERM.rolesView) || can(DEPT_PERM.rolesManage)
      ? [{ to: '/abteilung/rollen', label: t('Ämter') }]
      : []),
    ...(can(DEPT_PERM.entriesSubmit)
      ? [{ to: '/abteilung/meldungen', label: t('Meldungen') }]
      : []),
    ...(can(DEPT_PERM.export) ? [{ to: '/abteilung/export', label: t('Export') }] : []),
  ]
}
