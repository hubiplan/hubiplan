// Startseite als Arbeitsplatz je Rolle (Konzept S-04): feste Reihenfolge Zu erledigen ›
// Schnellaktionen › Kennzahlen › Nächste Termine › Hinweise. Die Rolle ergibt sich aus den
// Rechten; mehrere Rollen teilen sich höchstens vier Schnellaktionen, Kasse vor Vorstand.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { HomeFigure, OrgSummary } from '../../api/orgs.ts'
import { DEPT_PERM } from '../../api/portal.ts'
import type { DeptSummary } from '../../api/portal.ts'
import { euro } from '../../api/finance.ts'
import { imprintApi } from '../../api/imprint.ts'
import { letterheadApi, optionKey } from '../../api/letterhead.ts'
import { fieldApi } from '../../api/fields.ts'
import { BirthdayList, JubileeList } from '../../pages/members/JubileesPage.tsx'
import type { QuickAction } from './roleActions.ts'
import { MAX_ACTIONS, MAX_FIGURES, visibleActions } from './roleActions.ts'
import { homeActionsApi } from '../../api/homeActions.ts'
import { Alert, Checkbox } from '../ui.tsx'
import { todayIso } from '../../api/members.ts'
import { formatDay } from '../calendar/time.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { t } from '../../i18n/index.ts'

/**
 * Schnellaktionen (S-04): höchstens vier Knöpfe. Unter „Anpassen“ blendet jede Person einzelne
 * Aktionen oder den ganzen Block aus; wieder einschalten geht auch unter Mein Konto › Profil.
 */
export function QuickActions({ candidates, label }: { candidates: QuickAction[]; label?: string }) {
  const { data, error: loadError, setData } = useLoad(() => homeActionsApi.get(), [])
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (candidates.length === 0 || (!data && !loadError)) return null
  const hidden = data?.hidden ?? []
  const actions = visibleActions(candidates, hidden)
  if (hidden.includes('*')) return null

  async function save(next: string[]) {
    setBusy(true)
    setError(null)
    try {
      setData(await homeActionsApi.update(next))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggle = (key: string, shown: boolean) =>
    void save(shown ? hidden.filter((k) => k !== key) : [...hidden, key])

  return (
    <div className="card tile tile-wide home-actions">
      <div className="card-head">
        <h2>{label ?? t('Schnellaktionen')}</h2>
        <button
          type="button"
          className="link-button push-right"
          onClick={() => setEditing(!editing)}
        >
          {editing ? t('Fertig') : t('Anpassen')}
        </button>
      </div>
      {editing ? (
        <>
          <p className="muted small">
            {t('Gezeigt werden höchstens {n} der angehakten Aktionen.', { n: MAX_ACTIONS })}
          </p>
          <div className="home-actions-choice">
            {candidates.map((a) => (
              <Checkbox
                key={a.key}
                label={a.label}
                checked={!hidden.includes(a.key)}
                busy={busy}
                onChange={(v) => toggle(a.key, v)}
              />
            ))}
          </div>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => void save([...hidden, '*'])}
          >
            {t('Schnellaktionen ganz ausblenden')}
          </button>
          <p className="muted small">
            {t('Wieder einschalten kannst du sie unter Mein Konto › Profil › Startseite.')}
          </p>
        </>
      ) : actions.length === 0 ? (
        <p className="muted">{t('Alle Schnellaktionen sind ausgeblendet.')}</p>
      ) : (
        <div className="button-row">
          {actions.map((a, i) => (
            <Link key={a.key} to={a.to} className={i === 0 ? 'button button-primary' : 'button'}>
              {a.label}
            </Link>
          ))}
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

function figureValue(f: HomeFigure): string {
  if (f.kind === 'money') return euro(f.value)
  if (f.kind === 'date') return formatDay(String(f.value))
  return String(f.value)
}

export function FigureTiles({ figures }: { figures: HomeFigure[] }) {
  const shown = figures.slice(0, MAX_FIGURES)
  if (shown.length === 0) return null
  return (
    <div className="tile-wide home-figures" role="group" aria-label={t('Kennzahlen')}>
      <div className="tiles tiles-figures">
        {shown.map((f) => (
          <Link key={f.key} to={f.link} className="card tile home-figure">
            <span className="home-figure-label">{f.label}</span>
            <span className="amount-big">{figureValue(f)}</span>
            {f.detail && <span className="muted small">{f.detail}</span>}
          </Link>
        ))}
      </div>
    </div>
  )
}

/** Kennzahlen der Einheit (Verein, Dachverband) */
export function OrgFigures({ org }: { org: OrgSummary }) {
  const { data } = useLoad(() => orgApi.homeFigures(org.id), [org.id])
  return <FigureTiles figures={data?.figures ?? []} />
}

/** Kennzahl im Arbeitsbereich einer Untereinheit */
export function DeptFigures({ dept }: { dept: DeptSummary }) {
  const allowed = dept.permissions.includes(DEPT_PERM.membersView)
  const { data } = useLoad(
    () => (allowed ? orgApi.deptHomeFigures(dept.id) : Promise.resolve({ figures: [] })),
    [dept.id, allowed],
  )
  return <FigureTiles figures={data?.figures ?? []} />
}

interface Notice {
  key: string
  text: ReactNode
  to?: string
  link?: string
  onLater?: () => void
}

const NOTICE_DAYS = 30
const JUBILEE_DAYS = 90

function plusDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/**
 * Eine Karte „Hinweise (n)“ statt gestapelter Bänder (S-04): Impressum, Briefvorlage,
 * Jubiläen und Geburtstage. Ohne Hinweis keine Karte.
 */
export function NoticesCard({ org }: { org: OrgSummary | null }) {
  const today = todayIso()
  const until = plusDays(today, NOTICE_DAYS)
  const club = !!org && (org.type === 'club' || org.type === 'federation')
  const imprintShown = club && !!org && org.permissions.includes(PERM.orgEdit)
  const people =
    !!org &&
    org.type === 'club' &&
    org.modules.includes('members') &&
    org.permissions.includes(PERM.membersView)
  const imprint = useLoad(
    () => (imprintShown && org ? imprintApi.get(org.id) : Promise.resolve(null)),
    [org?.id, imprintShown],
  )
  const letters = useLoad(() => letterheadApi.mine(), [])
  const awards = people && !!org && org.modules.includes('awards')
  const jubilees = useLoad(
    () =>
      awards && org
        ? fieldApi.jubilees(org.id, today, plusDays(today, JUBILEE_DAYS))
        : Promise.resolve(null),
    [org?.id, awards, today],
  )
  const unitJubilees = useLoad(
    () =>
      awards && org
        ? fieldApi.unitJubilees(org.id, today, plusDays(today, JUBILEE_DAYS))
        : Promise.resolve(null),
    [org?.id, awards, today],
  )
  const birthdays = useLoad(
    () => (people && org ? fieldApi.birthdays(org.id, today, until) : Promise.resolve(null)),
    [org?.id, people, today],
  )
  const notices: Notice[] = []
  const missing = imprint.data?.missing ?? []
  if (missing.length > 0) {
    notices.push({
      key: 'imprint',
      text: t('Im Impressum fehlen noch Angaben: {x}.', { x: missing.join(', ') }),
      to: '/einstellungen/impressum',
      link: t('Impressum ergänzen'),
    })
  }
  for (const n of letters.data?.notices ?? []) {
    notices.push({
      key: `letter-${n.kind}-${n.context}-${n.unit.id}`,
      text:
        n.kind === 'outdated'
          ? `${t('Deine Briefvorlage für {name} ist veraltet:', { name: n.unit.name })} ${n.changes.join(', ')} ${t('geändert.')}`
          : t(
              'Für deine Funktion „{function}“ in {name} kannst du dir eine Briefvorlage erstellen.',
              {
                function: n.function,
                name: n.unit.name,
              },
            ),
      to: `/briefvorlage?fuer=${encodeURIComponent(optionKey(n.context, n.unit.id))}`,
      link: n.kind === 'outdated' ? t('Neu erstellen') : t('Jetzt erstellen'),
      onLater: () => void letterheadApi.dismiss(n.unit.id, n.context).then(letters.reload),
    })
  }
  const jubileeRows = jubilees.data?.results ?? []
  const unitRows = unitJubilees.data?.results ?? []
  if (jubileeRows.length + unitRows.length > 0) {
    notices.push({
      key: 'jubilees',
      text: (
        <>
          {t('Jubiläen in den nächsten {n} Tagen:', { n: JUBILEE_DAYS })}
          <JubileeList rows={jubileeRows} unitRows={unitRows} />
        </>
      ),
      to: '/mitglieder/jubilaeen',
      link: t('Alle Jubiläen'),
    })
  }
  const birthdayRows = birthdays.data?.results ?? []
  if (birthdayRows.length > 0) {
    notices.push({
      key: 'birthdays',
      text: (
        <>
          {t('Geburtstage in den nächsten {n} Tagen:', { n: NOTICE_DAYS })}
          <BirthdayList rows={birthdayRows} today={today} />
        </>
      ),
    })
  }
  if (notices.length === 0) return null
  return (
    <div className="card tile home-notices">
      <h2>
        {t('Hinweise')} <span className="badge">{notices.length}</span>
      </h2>
      <ul className="plain-list home-notice-list">
        {notices.map((n) => (
          <li key={n.key}>
            {n.text}
            {n.to && (
              <>
                {' '}
                <Link to={n.to}>{n.link}</Link>
              </>
            )}
            {n.onLater && (
              <>
                {' · '}
                <button type="button" className="link-button" onClick={n.onLater}>
                  {t('Später')}
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
