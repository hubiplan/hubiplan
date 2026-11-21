// Training und Anwesenheit in der Verwaltung (Verein und Untereinheit), mit Schießsport auch das
// Schießbuch (Lückenliste 20.11.2026, B1; docs/training.md).
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { PERM } from '../../api/orgs.ts'
import { trainingApi, trainingBase } from '../../api/training.ts'
import type { TrainingReport, TrainingSession } from '../../api/training.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Field, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { SessionDialog } from './SessionDialog.tsx'
import type { SessionForm } from './SessionDialog.tsx'
import { ShootingLog } from './ShootingLog.tsx'
import './training.css'

type View = 'sessions' | 'report' | 'shooting'

function isoDate(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function monthsBack(n: number) {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return isoDate(d)
}

export function timeLabel(s: TrainingSession) {
  if (!s.starts_at) return ''
  return s.ends_at ? `${s.starts_at}–${s.ends_at}` : s.starts_at
}

export function TrainingPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('training') : !!activeDept?.training_enabled
  if (
    !enabled ||
    !(permissions.includes(PERM.trainingView) || permissions.includes(PERM.trainingEdit))
  ) {
    return <NoAccessPage reason="right" />
  }
  const base = trainingBase(active?.id ?? null, active ? null : activeDept!.id)
  const shooting = !!active && active.modules.includes('shooting')
  return <Training key={base} base={base} orgId={active?.id ?? null} shooting={shooting} />
}

function Training({
  base,
  orgId,
  shooting,
}: {
  base: string
  orgId: number | null
  shooting: boolean
}) {
  const [view, setView] = useState<View>('sessions')
  const views: { id: View; label: string }[] = [
    { id: 'sessions', label: t('Trainings') },
    { id: 'report', label: t('Auswertung') },
    ...(shooting && orgId ? [{ id: 'shooting' as View, label: t('Schießbuch') }] : []),
  ]
  return (
    <div className="stack">
      <PageHeader
        subtitle={t(
          'Übungsabende und Trainings mit Anwesenheit. Mitglieder checken per QR-Code selbst ein, oder du hakst sie ab. Die Auswertung zeigt, wer wie oft da war.',
        )}
      />
      <div className="button-row training-views" role="group" aria-label={t('Ansicht')}>
        {views.map((v) => (
          <button
            key={v.id}
            type="button"
            className={view === v.id ? 'button' : 'button button-ghost'}
            aria-pressed={view === v.id}
            onClick={() => setView(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      {view === 'sessions' && <Sessions base={base} />}
      {view === 'report' && <Report base={base} />}
      {view === 'shooting' && orgId && <ShootingLog orgId={orgId} />}
    </div>
  )
}

function Sessions({ base }: { base: string }) {
  const [von, setVon] = useState(monthsBack(3))
  const [bis, setBis] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 30)
    return isoDate(d)
  })
  const { data, error, reload } = useLoad(() => trainingApi.list(base, von, bis), [base, von, bis])
  const options = useLoad(() => trainingApi.options(base), [base])
  const [open, setOpen] = useState<number | null>(null)
  const [creating, setCreating] = useState<Partial<SessionForm> | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data || !options.data) return <Loading />
  const canEdit = data.can_edit
  return (
    <div className="stack">
      {canEdit && (
        <div className="button-row">
          <button type="button" className="button button-primary" onClick={() => setCreating({})}>
            {t('Neues Training')}
          </button>
        </div>
      )}
      {canEdit && options.data.events.length > 0 && (
        <section className="card stack-sm">
          <h2>{t('Aus dem Kalender übernehmen')}</h2>
          <ul className="plain-list training-suggest">
            {options.data.events.map((e) => (
              <li key={`${e.event}-${e.date}`}>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() =>
                    setCreating({
                      event: e.event,
                      date: e.date,
                      starts_at: e.starts_at ?? '',
                      ends_at: e.ends_at ?? '',
                      title: e.title,
                      location: e.location,
                    })
                  }
                >
                  {formatDate(e.date)} {e.starts_at ?? ''} · {e.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="training-filter">
        <Field label={t('Von')} type="date" value={von} onChange={(e) => setVon(e.target.value)} />
        <Field label={t('Bis')} type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
      </div>
      {data.sessions.length === 0 ? (
        <EmptyList
          title={t('Keine Trainings im Zeitraum.')}
          canAdd={canEdit}
          action={{ label: t('Neues Training'), onClick: () => setCreating({}) }}
        >
          {t('Lege Übungsabende und Trainings an und erfasse, wer da war.')}
        </EmptyList>
      ) : (
        <SessionTable sessions={data.sessions} onOpen={setOpen} />
      )}
      {(open !== null || creating) && (
        <SessionDialog
          base={base}
          id={open}
          initial={creating ?? undefined}
          options={options.data}
          onClose={() => {
            setOpen(null)
            setCreating(null)
            void reload()
            void options.reload()
          }}
          onCreated={(id) => {
            setCreating(null)
            setOpen(id)
          }}
        />
      )}
    </div>
  )
}

function Report({ base }: { base: string }) {
  const [von, setVon] = useState(monthsBack(12))
  const [bis, setBis] = useState(isoDate(new Date()))
  const [error, setError] = useState('')
  const {
    data,
    error: loadError,
    reload,
  } = useLoad(() => trainingApi.report(base, von, bis), [base, von, bis])
  const download = async () => {
    setError('')
    try {
      saveBlob(await trainingApi.reportXlsx(base, von, bis), `anwesenheit-${von}-${bis}.xlsx`)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      <div className="training-filter">
        <Field label={t('Von')} type="date" value={von} onChange={(e) => setVon(e.target.value)} />
        <Field label={t('Bis')} type="date" value={bis} onChange={(e) => setBis(e.target.value)} />
        <button type="button" className="button button-ghost" onClick={download}>
          {t('Als Excel herunterladen')}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {loadError ? (
        <LoadError message={loadError} onRetry={reload} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <p role="status">
            {t('{sessions} Trainings mit zusammen {hours} Stunden, {attendances} Teilnahmen.', {
              sessions: data.total_sessions,
              hours: data.total_hours.toLocaleString(),
              attendances: data.total_attendances,
            })}
          </p>
          {data.members.length > 0 && <ReportTable members={data.members} />}
        </>
      )}
    </div>
  )
}

function SessionTable({
  sessions,
  onOpen,
}: {
  sessions: TrainingSession[]
  onOpen: (id: number) => void
}) {
  const search = useRowSearch(
    sessions,
    (s) => [s.title, s.kind_label, s.leader, s.discipline, s.department_name].join(' '),
    t('Trainings'),
  )
  const sort = useRowSort(search.shown, {
    date: (s) => s.date,
    title: (s) => s.title,
    kind: (s) => s.kind_label,
    leader: (s) => s.leader,
    count: (s) => s.count,
  })
  return (
    <>
      {search.field}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {sort.head('date', t('Datum'))}
              {sort.head('title', t('Bezeichnung'))}
              {sort.head('kind', t('Art'))}
              {sort.head('leader', t('Leitung'))}
              {sort.head('count', t('Anwesend'), { className: 'num' })}
            </tr>
          </thead>
          <tbody>
            {sort.rows.map((s) => (
              <tr key={s.id}>
                <td>
                  {formatDate(s.date)} <span className="muted small">{timeLabel(s)}</span>
                </td>
                <td>
                  <button type="button" className="link-button" onClick={() => onOpen(s.id)}>
                    {s.title}
                  </button>
                  {s.shooting && <span className="muted small"> · {s.discipline}</span>}
                  {s.checkin_open && (
                    <span className="badge badge-info">{t('Einchecken offen')}</span>
                  )}
                </td>
                <td>{s.kind_label}</td>
                <td>{s.leader}</td>
                <td className="num">{s.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function ReportTable({ members }: { members: TrainingReport['members'] }) {
  const search = useRowSearch(members, (m) => m.name, t('Teilnahmen'))
  const sort = useRowSort(search.shown, {
    name: (m) => m.name,
    count: (m) => m.count,
    share: (m) => m.share,
  })
  return (
    <>
      {search.field}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {sort.head('name', t('Name'))}
              {sort.head('count', t('Teilnahmen'), { className: 'num' })}
              {sort.head('share', t('Anteil'), { className: 'num' })}
            </tr>
          </thead>
          <tbody>
            {sort.rows.map((m) => (
              <tr key={m.membership}>
                <td>{m.name}</td>
                <td className="num">{m.count}</td>
                <td className="num">{m.share} %</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
