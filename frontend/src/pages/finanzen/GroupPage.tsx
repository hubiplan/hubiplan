// Gruppenseite der Finanzen (Konzept S-01, F2): Kurzbeschreibung je Eintrag, was dort zu
// erledigen ist, und die Hauptaktion der Gruppe. „Zu erledigen“ kommt aus derselben Quelle
// wie auf der Startseite und der Übersicht.
import { Link, Navigate } from 'react-router-dom'
import { orgApi } from '../../api/orgs.ts'
import type { OpenTask } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { financeGroupList } from './access.ts'
import type { FinanceAccess } from './access.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { t } from '../../i18n/index.ts'

interface Action {
  to: string
  label: string
}

/** Hauptaktionen je Gruppe, nur mit Recht zum Bearbeiten. */
function groupActions(key: string, a: FinanceAccess): Action[] {
  switch (key) {
    case 'abrechnen':
      return a.billingEdit
        ? [{ to: '/finanzen/rechnungen?rechnung=neu', label: t('Rechnung schreiben') }]
        : []
    case 'zahlungen':
      if (a.financeEdit)
        return [{ to: '/finanzen/kontoauszuege', label: t('Kontoauszug einlesen') }]
      return a.sepa && a.billingEdit
        ? [{ to: '/finanzen/lastschrift', label: t('Lastschriftlauf anlegen') }]
        : []
    case 'buchen':
      return a.financeEdit
        ? [
            { to: '/finanzen/kassenbuch?buchung=neu-einnahme', label: t('Einnahme erfassen') },
            { to: '/finanzen/kassenbuch?buchung=neu-ausgabe', label: t('Ausgabe erfassen') },
          ]
        : []
    case 'abschliessen':
      return a.finance ? [{ to: '/finanzen/abschluss', label: t('Jahr abschließen') }] : []
    default:
      return []
  }
}

const covers = (parent: string, path: string) => path === parent || path.startsWith(`${parent}/`)

/** Offene Aufgaben dem Eintrag zuordnen, dessen Pfad am tiefsten passt. */
function tasksFor(to: string, all: string[], tasks: OpenTask[]): OpenTask[] {
  return tasks.filter((task) => {
    const path = task.link.split(/[?#]/)[0]
    const best = all.filter((p) => covers(p, path)).sort((x, y) => y.length - x.length)[0]
    return best === to
  })
}

export function FinanceGroupPage({
  groupKey,
  access: a,
}: {
  groupKey: string
  access: FinanceAccess
}) {
  const org = useActiveOrg()
  const group = financeGroupList(a).find((g) => g.key === groupKey)
  const { data } = useLoad(() => orgApi.openTasks(org.id), [org.id])
  if (!group) return <Navigate to="/finanzen" replace />
  const tasks = (data?.items ?? []).filter((task) => task.area === 'finance')
  const paths = group.items.map((i) => i.to)
  const actions = groupActions(group.key, a)
  return (
    <section>
      {/* h1 = Gruppe, Pfad „Finanzen › Gruppe“ aus dem Menü (S-05) */}
      <PageHeader
        primary={actions[0] ? { label: actions[0].label, to: actions[0].to } : null}
        actions={actions.slice(1).map((act) => ({ label: act.label, to: act.to }))}
      />
      {group.text && <p className="muted">{group.text}</p>}
      <ul className="group-cards">
        {group.items.map((item) => {
          const open = tasksFor(item.to, paths, tasks)
          return (
            <li key={item.to}>
              <Link to={item.to}>
                <strong>{item.label}</strong>
                {item.text && <span>{item.text}</span>}
                {open.map((task, i) => (
                  <span key={`${task.kind}-${task.ref ?? i}`} className="group-card-todo">
                    {task.title}
                  </span>
                ))}
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
