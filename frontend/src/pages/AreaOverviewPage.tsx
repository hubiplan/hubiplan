// Bereichsübersicht (Konzept Web-Oberfläche W4): alle Seiten eines Bereichs mit einem Satzteil,
// was man dort tut, und dem, was dort gerade zu erledigen ist. Erreichbar über den Namen des
// Bereichs oben im Bereichsmenü; die Einträge folgen dem Menü der Person.
import { Link, Navigate, useParams } from 'react-router-dom'
import { orgApi } from '../api/orgs.ts'
import type { OpenTask } from '../api/orgs.ts'
import { useLoad } from '../components/forms.ts'
import { PageHeader } from '../components/PageHeader.tsx'
import { AREAS, modules } from '../modules.tsx'
import { useOrg } from '../org/OrgContext.tsx'
import { t } from '../i18n/index.ts'

const covers = (parent: string, path: string) => path === parent || path.startsWith(`${parent}/`)

export function AreaOverviewPage() {
  const { area: areaId } = useParams()
  const { active, activeDept, activePortal } = useOrg()
  const orgId = active?.id ?? null
  const { data } = useLoad(
    () => (orgId === null ? Promise.resolve({ items: [] as OpenTask[] }) : orgApi.openTasks(orgId)),
    [orgId],
  )
  const area = AREAS.find((a) => a.id === areaId)
  const ws = { dept: activeDept, portal: activePortal }
  const items = modules.filter((m) => m.area === areaId && m.visible(active, ws))
  if (!area || items.length === 0 || activePortal) return <Navigate to="/" replace />
  const paths = items.flatMap((m) => [m.path, ...(m.also ?? [])])
  // Offene Einträge dem Menüpunkt zuordnen, dessen Pfad am tiefsten passt
  const tasksFor = (own: string[]) =>
    (data?.items ?? []).filter((task) => {
      const path = task.link.split(/[?#]/)[0]
      const best = paths.filter((p) => covers(p, path)).sort((x, y) => y.length - x.length)[0]
      return !!best && own.includes(best)
    })
  return (
    <section>
      <PageHeader title={area.label} subtitle={t('Alle Seiten dieses Bereichs auf einen Blick.')} />
      <ul className="group-cards">
        {items.map((m) => {
          const open = tasksFor([m.path, ...(m.also ?? [])])
          return (
            <li key={m.id}>
              <Link to={m.linkFor?.(active, ws) ?? m.path}>
                <strong>
                  {m.id === 'abteilung' && activeDept
                    ? activeDept.label
                    : (m.labelFor?.(active, ws) ?? m.label)}
                </strong>
                {m.text && <span>{m.text}</span>}
                {open.slice(0, 3).map((task, i) => (
                  <span key={`${task.kind}-${task.ref ?? i}`} className="group-card-todo">
                    {task.title}
                  </span>
                ))}
                {open.length > 3 && (
                  <span className="group-card-todo">
                    {t('und {n} weitere', { n: open.length - 3 })}
                  </span>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
