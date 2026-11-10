import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { useOrg } from '../org/OrgContext.tsx'
import { calendarBase } from '../api/events.ts'
import { UpcomingTile } from '../components/calendar/UpcomingTile.tsx'
import { DepartmentTodosTile } from '../components/DepartmentTodosTile.tsx'
import { OpenTasksTile } from '../components/OpenTasksTile.tsx'
import { PERM } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import {
  BirthdaysCard,
  JubileesCard,
  NoticesCard,
  QuickActions,
} from '../components/home/RoleHome.tsx'
import { HomeBoard } from '../components/home/HomeBoard.tsx'
import { BLOCK, hasBirthdays, hasJubilees } from '../components/home/homeLayout.ts'
import type { HomeBlock } from '../components/home/homeLayout.ts'
import {
  actionCatalog,
  actionScope,
  deptActions,
  deptCatalog,
  roleActionCandidates,
} from '../components/home/roleActions.ts'
import { PortalTasks } from './portal/PortalPage.tsx'
import { MemberHomeTop } from '../components/home/MemberHome.tsx'
import { t } from '../i18n/index.ts'

/** Rechte, mit denen es etwas zu erledigen geben kann (Entscheidungen, überfällige Rechnungen) */
const TASK_PERMS = [
  PERM.membersEdit,
  PERM.photosManage,
  PERM.eventsManage,
  PERM.billingView,
  // Belegungsanfragen, Kontaktformular, Rundschreiben-Entwürfe (Menüprüfung M-13)
  PERM.bookingsEdit,
  PERM.materialEdit,
  PERM.infrastructureEdit,
  PERM.websiteManage,
  PERM.circularsSend,
  // Kassenführung, Versammlungen und Einrichtung (S-04 H3, S-02)
  PERM.financeEdit,
  PERM.meetingsEdit,
  PERM.settingsView,
]

function showsOpenTasks(org: OrgSummary): boolean {
  if (org.permissions.includes('todos.view')) return true
  if (org.type !== 'club' && org.type !== 'federation') return false
  return TASK_PERMS.some((p) => org.permissions.includes(p))
}

export function HomePage() {
  const { user } = useAuth()
  const { active, activeDept, activePortal } = useOrg()

  if (!active && activeDept) {
    return (
      <section>
        <h1 className="sr-only">{activeDept.name}</h1>
        {/* Standard wie im Verein (S-04): Zu erledigen, Schnellaktionen, Termine, Hinweise;
            jede Person ordnet selbst */}
        <HomeBoard
          scope={actionScope.dept(activeDept)}
          name={activeDept.name}
          blocks={(prefs) => {
            const list: HomeBlock[] = []
            if (activeDept.permissions.includes('todos.view'))
              list.push({
                key: BLOCK.deptTodos,
                label: t('Offene Aufgaben'),
                render: () => <DepartmentTodosTile department={activeDept.id} />,
              })
            if (deptCatalog(activeDept).length > 0)
              list.push({
                key: BLOCK.actions,
                label: t('Schnellaktionen'),
                wide: true,
                render: () => (
                  <QuickActions
                    candidates={deptActions(activeDept)}
                    catalog={deptCatalog(activeDept)}
                    scope={actionScope.dept(activeDept)}
                    label={t('Schnellaktionen: {label}', { label: activeDept.label })}
                    prefs={prefs}
                  />
                ),
              })
            if (activeDept.events_enabled)
              list.push({
                key: BLOCK.upcoming,
                label: t('Nächste Termine'),
                render: () => <UpcomingTile base={calendarBase.dept(activeDept.id)} />,
              })
            list.push({
              key: BLOCK.notices,
              label: t('Hinweise'),
              render: () => <NoticesCard org={null} />,
            })
            return list
          }}
        />
      </section>
    )
  }

  if (!active && activePortal) {
    return (
      <section>
        <h1>
          {t('Hallo')} {activePortal.first_name}
        </h1>
        <MemberHomeTop entry={activePortal} />
        <h2 className="section-heading">{t('Mein Bereich')}</h2>
        {/* W-07: nur die wichtigsten Kacheln, der Rest steht in „Mein Bereich“ */}
        {/* S-04: höchstens vier Kacheln, der Ausweis zuerst; Termine stehen schon oben */}
        <PortalTasks
          entry={activePortal}
          skip={['/termine']}
          prefer={[
            '/mein-bereich/ausweis',
            '/mein-bereich/helferdienste',
            '/mein-bereich/rechnungen',
          ]}
          limit={4}
        />
        <p>
          <Link to="/mein-bereich">{t('Alles in Mein Bereich')}</Link>
        </p>
        {activeDept?.permissions.includes('todos.view') && (
          <div className="tiles">
            <DepartmentTodosTile department={activeDept.id} />
          </div>
        )}
      </section>
    )
  }

  if (!active) {
    return (
      <section>
        <h1>{t('Willkommen')}</h1>
        <div className="card">
          <p>
            {t('Deinem Konto ({email}) ist noch keine Organisation zugeordnet.', {
              email: user?.email,
            })}
          </p>
          <p className="muted small">
            {t(
              'Bitte wende dich an deinen Vorstand. Dein Konto und die Zwei-Faktor-Anmeldung verwaltest du hier:',
            )}{' '}
            <Link to="/mein-konto/anmeldung">{t('Mein Konto › Anmeldung & Sicherheit')}</Link>.
          </p>
        </div>
      </section>
    )
  }

  // Name und Dachverband stehen schon im Kopf; die Überschrift ist nur für Screenreader.
  // Standardreihenfolge für alle Rollen (S-04): Zu erledigen › Schnellaktionen › Nächste
  // Termine › Jubiläen › Geburtstage › Hinweise. Was die Person nicht darf, fehlt einfach;
  // den Rest stellt sie sich unter „Startseite anpassen“ selbst zusammen.
  const org = active
  const clubLike = org.type === 'club' || org.type === 'federation'
  const upcoming =
    clubLike &&
    org.modules.includes('events') &&
    // Ohne Recht auf den Kalender keine Kachel und keine abgelehnte Anfrage (W-01)
    org.permissions.includes(PERM.eventsView)
  const people =
    org.type === 'club' &&
    org.modules.includes('members') &&
    org.permissions.includes(PERM.membersView)
  const catalog = actionCatalog(org)
  const dept = activeDept
  return (
    <section>
      <h1 className="sr-only">{org.name}</h1>
      <HomeBoard
        scope={actionScope.org(org)}
        name={org.name}
        blocks={(prefs) => {
          const list: HomeBlock[] = []
          if (dept?.permissions.includes('todos.view'))
            list.push({
              key: BLOCK.deptTodos,
              label: t('Offene Aufgaben: {name}', { name: dept.name }),
              render: () => <DepartmentTodosTile department={dept.id} />,
            })
          if (showsOpenTasks(org))
            list.push({
              key: BLOCK.tasks,
              label: t('Zu erledigen'),
              wide: true,
              render: () => <OpenTasksTile org={org} />,
            })
          if (catalog.length > 0)
            list.push({
              key: BLOCK.actions,
              label: t('Schnellaktionen'),
              wide: true,
              render: () => (
                <QuickActions
                  candidates={roleActionCandidates(org)}
                  catalog={catalog}
                  scope={actionScope.org(org)}
                  prefs={prefs}
                />
              ),
            })
          if (upcoming)
            list.push({
              key: BLOCK.upcoming,
              label: t('Nächste Termine'),
              render: () => <UpcomingTile base={calendarBase.org(org.id)} />,
            })
          if (hasJubilees(org))
            list.push({
              key: BLOCK.jubilees,
              label: t('Jubiläen'),
              render: () => <JubileesCard org={org} />,
            })
          if (hasBirthdays(org))
            list.push({
              key: BLOCK.birthdays,
              label: t('Geburtstage'),
              render: () => <BirthdaysCard org={org} />,
            })
          list.push({
            key: BLOCK.notices,
            label: t('Hinweise'),
            render: () => <NoticesCard org={org} />,
          })
          return list
        }}
      >
        {!upcoming && !people && catalog.length === 0 && (
          <div className="card tile">
            <h2>{t('Übersicht')}</h2>
            <p className="muted">{t('Hier erscheinen Kacheln der Module.')}</p>
          </div>
        )}
      </HomeBoard>
    </section>
  )
}
