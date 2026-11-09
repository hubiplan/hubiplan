import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { useOrg } from '../org/OrgContext.tsx'
import { calendarBase } from '../api/events.ts'
import { UpcomingTile } from '../components/calendar/UpcomingTile.tsx'
import { DepartmentTodosTile } from '../components/DepartmentTodosTile.tsx'
import { OpenTasksTile } from '../components/OpenTasksTile.tsx'
import { PERM } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { DeptFigures, NoticesCard, OrgFigures, QuickActions } from '../components/home/RoleHome.tsx'
import { deptActions, roleActions } from '../components/home/roleActions.ts'
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
        {/* Gleiche Reihenfolge wie im Verein (S-04): Zu erledigen, Schnellaktionen, Kennzahl,
            Termine, Hinweise */}
        <div className="tiles home-grid">
          {activeDept.permissions.includes('todos.view') && (
            <DepartmentTodosTile department={activeDept.id} />
          )}
          <QuickActions
            actions={deptActions(activeDept)}
            label={t('Schnellaktionen: {label}', { label: activeDept.label })}
          />
          <DeptFigures dept={activeDept} />
          {activeDept.events_enabled && <UpcomingTile base={calendarBase.dept(activeDept.id)} />}
          <NoticesCard org={null} />
        </div>
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
  // Feste Reihenfolge für alle Rollen (S-04): Zu erledigen › Schnellaktionen › Kennzahlen ›
  // Nächste Termine › Hinweise. Was die Person nicht darf, fehlt einfach.
  const actions = roleActions(active)
  const clubLike = active.type === 'club' || active.type === 'federation'
  const upcoming =
    clubLike &&
    active.modules.includes('events') &&
    // Ohne Recht auf den Kalender keine Kachel und keine abgelehnte Anfrage (W-01)
    active.permissions.includes(PERM.eventsView)
  const people =
    active.type === 'club' &&
    active.modules.includes('members') &&
    active.permissions.includes(PERM.membersView)
  return (
    <section>
      <h1 className="sr-only">{active.name}</h1>
      <div className="tiles home-grid">
        {activeDept?.permissions.includes('todos.view') && (
          <DepartmentTodosTile department={activeDept.id} />
        )}
        {showsOpenTasks(active) && <OpenTasksTile org={active} />}
        <QuickActions actions={actions} />
        {clubLike && <OrgFigures org={active} />}
        {upcoming && <UpcomingTile base={calendarBase.org(active.id)} />}
        <NoticesCard org={active} />
        {!upcoming && !people && actions.length === 0 && (
          <div className="card tile">
            <h2>{t('Übersicht')}</h2>
            <p className="muted">{t('Hier erscheinen Kacheln der Module.')}</p>
          </div>
        )}
      </div>
    </section>
  )
}
