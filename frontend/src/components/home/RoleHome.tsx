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
import type { BirthdayRow } from '../../api/fields.ts'
import type { QuickAction } from './roleActions.ts'
import { MAX_FIGURES } from './roleActions.ts'
import { todayIso } from '../../api/members.ts'
import { useLoad } from '../forms.ts'
import { formatDay } from '../calendar/time.ts'
import { t } from '../../i18n/index.ts'

export function QuickActions({ actions, label }: { actions: QuickAction[]; label?: string }) {
  if (actions.length === 0) return null
  return (
    <div className="card tile tile-wide home-actions">
      <h2>{label ?? t('Schnellaktionen')}</h2>
      <div className="button-row">
        {actions.map((a, i) => (
          <Link key={a.key} to={a.to} className={i === 0 ? 'button button-primary' : 'button'}>
            {a.label}
          </Link>
        ))}
      </div>
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
  const jubilees = useLoad(
    () =>
      people && org && org.modules.includes('awards')
        ? fieldApi.jubilees(org.id, today, until)
        : Promise.resolve(null),
    [org?.id, people, today],
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
          ? t('Deine Briefvorlage für {name} ist veraltet.', { name: n.unit.name })
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
  const jubileeCount = new Set((jubilees.data?.results ?? []).map((r) => r.member_id)).size
  if (jubileeCount > 0) {
    notices.push({
      key: 'jubilees',
      text:
        jubileeCount === 1
          ? t('1 Jubiläum in den nächsten {n} Tagen', { n: NOTICE_DAYS })
          : t('{count} Jubiläen in den nächsten {n} Tagen', {
              count: jubileeCount,
              n: NOTICE_DAYS,
            }),
      to: '/mitglieder/jubilaeen',
      link: t('ansehen'),
    })
  }
  const birthdayRows = birthdays.data?.results ?? []
  if (birthdayRows.length > 0) {
    notices.push({
      key: 'birthdays',
      text: <BirthdayNotice rows={birthdayRows} today={today} />,
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
            <span>{n.text}</span>
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

const BIRTHDAY_PREVIEW = 3

/** Geburtstage als Hinweis: Namen mit Link zur Akte, weitere aufklappbar. */
function BirthdayNotice({ rows, today }: { rows: BirthdayRow[]; today: string }) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, BIRTHDAY_PREVIEW)
  return (
    <>
      {rows.length === 1
        ? t('Geburtstag in den nächsten {n} Tagen:', { n: NOTICE_DAYS })
        : t('{count} Geburtstage in den nächsten {n} Tagen:', {
            count: rows.length,
            n: NOTICE_DAYS,
          })}{' '}
      {shown.map((r, i) => (
        <span key={`${r.member_id}-${r.date}`}>
          {i > 0 && ', '}
          <Link to={`/mitglieder/${r.member_id}`}>
            {r.first_name} {r.last_name}
          </Link>{' '}
          <span className="muted small">
            ({r.date === today ? t('heute') : formatDay(r.date)}, {r.age})
          </span>
        </span>
      ))}
      {rows.length > BIRTHDAY_PREVIEW && (
        <>
          {' '}
          <button type="button" className="link-button" onClick={() => setAll(!all)}>
            {all ? t('weniger') : t('alle {n} zeigen', { n: rows.length })}
          </button>
        </>
      )}
    </>
  )
}
