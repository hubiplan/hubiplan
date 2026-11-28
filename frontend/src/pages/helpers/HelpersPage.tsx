// Helferdienste und Schichtpläne (konzepte/helferdienste.md, Schritte H1–H3): Dienstpläne,
// Dienste, Schichten mit Schnelleingabe, Einteilung durch die Verwaltung, Druck und Export,
// Kontingente für Untereinheiten, Kopie, Aufruf per Rundschreiben und geleistete Dienste (H4).
import { PERM } from '../../api/orgs.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import './helpers.css'
import { NoAccessPage } from '../NoticePages.tsx'
import { Plans } from './Plans.tsx'

export function HelpersPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('helpers') : !!activeDept?.helpers_enabled
  if (!enabled || !permissions.includes(PERM.helpersView)) {
    return <NoAccessPage reason="right" />
  }
  const base = active ? `/api/orgs/${active.id}/helpers/` : `/api/depts/${activeDept!.id}/helpers/`
  return (
    <Plans
      key={base}
      base={base}
      orgId={active?.id ?? activeDept!.id}
      canEdit={permissions.includes(PERM.helpersEdit)}
    />
  )
}
