import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.tsx'
import { useOrg } from '../org/OrgContext.tsx'
import { calendarBase } from '../api/events.ts'
import { UpcomingTile } from '../components/calendar/UpcomingTile.tsx'
import { DepartmentTodosTile } from '../components/DepartmentTodosTile.tsx'
import { OpenTasksTile } from '../components/OpenTasksTile.tsx'
import { PERM } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import type { PortalEntry } from '../api/portal.ts'
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
import { NextEventCard, OpenInvoiceNotice } from '../components/home/MemberHome.tsx'
import { tileBlocks } from '../components/home/TileCard.tsx'
import { homeTilesApi } from '../api/homeTiles.ts'
import { useLoad } from '../components/forms.ts'
import { locale, t } from '../i18n/index.ts'

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
    return <MemberHomePage />
  }

  if (!active) {
    return (
      <section>
        <h1>{t('Willkommen')}</h1>
        <div className="card">
          <p>
            {t('Deinem Konto ({email}) ist noch keine Einheit zugeordnet.', {
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

  return <OrgHome org={active} />
}

/** Datum und Begrüßung über der Startseite (Web-Oberfläche W10, wie „Mein Verein“). */
function HomeGreeting({ name }: { name?: string }) {
  const [now] = useState(() => new Date())
  const hour = now.getHours()
  const first = name && !name.includes('@') ? name.trim().split(/\s+/)[0] : ''
  let greeting: string
  if (hour < 11) greeting = first ? t('Guten Morgen, {name}', { name: first }) : t('Guten Morgen')
  else if (hour < 18) greeting = first ? t('Guten Tag, {name}', { name: first }) : t('Guten Tag')
  else greeting = first ? t('Guten Abend, {name}', { name: first }) : t('Guten Abend')
  return (
    <div className="home-greeting">
      <p className="home-date muted small">
        {new Intl.DateTimeFormat(locale(), {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        }).format(now)}
      </p>
      <p className="home-greeting-text">{greeting}</p>
    </div>
  )
}

/**
 * Startseite der Verwaltung einer Einheit. Name und Dachverband stehen schon im Kopf; die
 * Überschrift ist nur für Screenreader. Standardreihenfolge für alle Rollen (S-04): Zu erledigen
 * › Kacheln mit Anlass › Schnellaktionen › Nächste Termine › Jubiläen › Geburtstage › Hinweise.
 * Was die Person nicht darf, fehlt einfach; den Rest stellt sie sich unter „Startseite anpassen“
 * selbst zusammen. Kacheln bei Anlass (backend/hometiles) erscheinen ohne eigene Wahl nur, wenn
 * gerade etwas ansteht.
 */
function OrgHome({ org }: { org: OrgSummary }) {
  const { user } = useAuth()
  const { activeDept } = useOrg()
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
  // Kacheln bei Anlass (backend/hometiles); ohne Antwort einfach ohne sie
  const tiles = useLoad(() => homeTilesApi.org(org.id), [org.id])
  return (
    <section>
      <h1 className="sr-only">{org.name}</h1>
      <HomeBoard
        scope={actionScope.org(org)}
        intro={<HomeGreeting name={user?.display} />}
        name={org.name}
        onSaved={tiles.reload}
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
          // Was gerade ansteht, steht oben
          list.push(...tileBlocks(tiles.data))
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
        {!upcoming &&
          !people &&
          catalog.length === 0 &&
          (user?.mfa_overdue ? (
            // VW-37: ruhende Rechte ohne Platzhalter, mit dem einen nächsten Schritt
            <div className="card tile" data-testid="mfa-schritt">
              <h2>{t('Zwei-Faktor-Anmeldung einrichten')}</h2>
              <p>
                {t(
                  'Deine Verwaltungsrechte ruhen, bis die Zwei-Faktor-Anmeldung eingerichtet ist. Danach siehst du wieder alle Bereiche.',
                )}
              </p>
              <div className="button-row">
                <Link to="/mein-konto/anmeldung#zwei-faktor" className="button button-primary">
                  {t('Jetzt einrichten')}
                </Link>
              </div>
            </div>
          ) : (
            <div className="card tile">
              <h2>{t('Übersicht')}</h2>
              <p className="muted">
                {t(
                  'Für diese Einheit sind noch keine Bereiche für dich freigeschaltet. Wer bei euch die Rollen vergibt, kann das ändern.',
                )}
              </p>
            </div>
          ))}
      </HomeBoard>
    </section>
  )
}

/**
 * Startseite im Mitgliederbereich: wie in der Verwaltung selbst zusammenstellbar (Bereich
 * „p<Zugang>“), mit nächstem Termin, „Mein Bereich“ und den Kacheln bei Anlass.
 */
function MemberHomePage() {
  const { activePortal, activeDept } = useOrg()
  const entry = activePortal as PortalEntry
  const tiles = useLoad(() => homeTilesApi.portal(entry.id), [entry.id])
  return (
    <section>
      {/* Design „Frisch“ D5: Datum über der Begrüßung */}
      <p className="home-date muted small">
        {new Intl.DateTimeFormat(locale(), {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        }).format(new Date())}
      </p>
      <h1>
        {t('Hallo')} {entry.first_name}
      </h1>
      <OpenInvoiceNotice access={entry.id} />
      <HomeBoard
        scope={`p${entry.id}`}
        name={entry.club_display_name || entry.club_name}
        onSaved={tiles.reload}
        blocks={() => {
          const list: HomeBlock[] = []
          // S-04: der nächste Termin mit Zu-/Absage ganz oben, auch am Handy (W-19)
          if (entry.events_enabled)
            list.push({
              key: BLOCK.nextEvent,
              label: t('Nächster Termin'),
              render: () => <NextEventCard access={entry.id} />,
            })
          list.push(...tileBlocks(tiles.data))
          list.push({
            key: BLOCK.memberArea,
            label: t('Mein Bereich'),
            wide: true,
            render: () => (
              <div className="home-member-area">
                <h2 className="section-heading">{t('Mein Bereich')}</h2>
                {/* W-07/S-04: höchstens vier Kacheln, der Ausweis zuerst; Termine stehen oben */}
                <PortalTasks
                  entry={entry}
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
              </div>
            ),
          })
          if (activeDept?.permissions.includes('todos.view')) {
            const dept = activeDept
            list.push({
              key: BLOCK.deptTodos,
              label: t('Offene Aufgaben'),
              render: () => <DepartmentTodosTile department={dept.id} />,
            })
          }
          return list
        }}
      />
    </section>
  )
}
