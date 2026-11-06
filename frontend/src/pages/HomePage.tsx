import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { useOrg } from '../org/OrgContext.tsx'
import { calendarBase } from '../api/events.ts'
import { UpcomingTile } from '../components/calendar/UpcomingTile.tsx'
import { BirthdayTile, JubileeTile } from './members/JubileesPage.tsx'
import { DepartmentTodosTile } from '../components/DepartmentTodosTile.tsx'
import { OpenTasksTile } from '../components/OpenTasksTile.tsx'
import { imprintApi } from '../api/imprint.ts'
import { PERM } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { useLoad } from '../components/forms.ts'
import { ImprintMissing } from './settings/ImprintSettingsPage.tsx'
import { HomeLetterheadNotices } from './LetterheadPage.tsx'

/** Vorstand: Hinweis, wenn im Impressum Pflichtangaben fehlen. */
function ImprintHint({ org }: { org: OrgSummary }) {
  const show =
    (org.type === 'club' || org.type === 'federation') && org.permissions.includes(PERM.orgEdit)
  const { data } = useLoad(
    () => (show ? imprintApi.get(org.id) : Promise.resolve(null)),
    [org.id, show],
  )
  return data ? <ImprintMissing missing={data.missing} /> : null
}
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
        <HomeLetterheadNotices />
        <div className="tiles">
          {activeDept?.permissions.includes('todos.view') && (
            <DepartmentTodosTile department={activeDept.id} />
          )}
          <div className="card tile">
            <h2>{activeDept.label}</h2>
            <p>
              <Link to="/abteilung">
                {t('Mitglieder der {label} ansehen', { label: activeDept.label })}
              </Link>
            </p>
            <p>
              <Link to="/briefvorlage">{t('Briefvorlage erstellen')}</Link>
            </p>
          </div>
          {activeDept.events_enabled && <UpcomingTile base={calendarBase.dept(activeDept.id)} />}
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
        <PortalTasks entry={activePortal} skip={['/mein-bereich/ausweis', '/termine']} />
        {activePortal.events_enabled && (
          <div className="tiles">
            {activeDept?.permissions.includes('todos.view') && (
              <DepartmentTodosTile department={activeDept.id} />
            )}
            <UpcomingTile base={calendarBase.portal(activePortal.id)} />
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
  return (
    <section>
      <h1 className="sr-only">{active.name}</h1>
      <ImprintHint org={active} />
      <HomeLetterheadNotices />
      <div className="tiles">
        {activeDept?.permissions.includes('todos.view') && (
          <DepartmentTodosTile department={activeDept.id} />
        )}
        {showsOpenTasks(active) && <OpenTasksTile org={active} />}
        {(active.type === 'club' || active.type === 'federation') &&
          active.modules.includes('events') && <UpcomingTile base={calendarBase.org(active.id)} />}
        {active.type === 'club' &&
        active.modules.includes('members') &&
        active.permissions.includes('members.view') ? (
          <>
            <JubileeTile />
            <BirthdayTile />
          </>
        ) : (
          !active.modules.includes('events') && (
            <div className="card tile">
              <h2>{t('Übersicht')}</h2>
              <p className="muted">{t('Hier erscheinen Kacheln der Module.')}</p>
            </div>
          )
        )}
      </div>
    </section>
  )
}
