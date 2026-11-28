// Versammlungen und Sitzungen (konzepte/versammlungen.md, Schritte V1–V7): Übersicht,
// Anlegen mit Termin, Tagesordnung, Einladung, Anwesenheit, Protokoll, Arten, Beschlussbuch.
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { meetingApi } from '../../api/meetings.ts'
import type { Meeting, MeetingKind } from '../../api/meetings.ts'
import { useDetailParam } from '../../components/detailParam.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { PERM } from '../../api/orgs.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { ResolutionBook } from './ResolutionBook.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import './meetings.css'
import { PlaceField } from '../../components/PlaceField.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { MeetingDetail } from './MeetingDetail.tsx'
import { statusLabel, when } from './meetingsHelpers.ts'
import { KindsCard } from './KindsCard.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'

export function MeetingsPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('meetings') : !!activeDept?.meetings_enabled
  if (!enabled || !permissions.includes(PERM.meetingsView)) {
    return <NoAccessPage reason="right" />
  }
  const base = active
    ? `/api/orgs/${active.id}/meetings/`
    : `/api/depts/${activeDept!.id}/meetings/`
  // Wahlen ins Amt übernehmen: nur im Verein und mit Rollenverwaltung (Ämter der
  // Untereinheiten besetzt deren eigene Rollenseite)
  const assignOrg = active && permissions.includes(PERM.rolesManage) ? active.id : null
  return (
    <Meetings
      key={base}
      base={base}
      canEdit={permissions.includes(PERM.meetingsEdit)}
      assignOrg={assignOrg}
    />
  )
}

function Meetings({
  base,
  canEdit,
  assignOrg,
}: {
  base: string
  canEdit: boolean
  assignOrg: number | null
}) {
  const [params, setParams] = useSearchParams()
  const view =
    params.get('ansicht') === 'arten'
      ? 'kinds'
      : params.get('ansicht') === 'beschluesse'
        ? 'book'
        : 'list'
  const detail = useDetailParam('versammlung')
  const list = useLoad(() => meetingApi.list(base), [base])
  const kinds = useLoad(() => meetingApi.kinds(base), [base])
  // Schnellaktion „Versammlung anlegen“ der Startseite (S-04): ?neu=1 öffnet das Formular
  const [creating, setCreating] = useState(() => canEdit && params.get('neu') === '1')
  useEffect(() => {
    if (params.get('neu') !== '1') return
    const next = new URLSearchParams(params)
    next.delete('neu')
    setParams(next, { replace: true })
  }, [params, setParams])
  const [now] = useState(() => Date.now())
  const show = (next: 'list' | 'kinds' | 'book') => {
    const p = new URLSearchParams(params)
    if (next === 'kinds') p.set('ansicht', 'arten')
    else if (next === 'book') p.set('ansicht', 'beschluesse')
    else p.delete('ansicht')
    setParams(p)
  }
  if (detail.value) {
    return (
      <MeetingDetail
        base={base}
        id={Number(detail.value)}
        kinds={kinds.data ?? []}
        onClose={async () => {
          detail.close()
          await list.reload()
        }}
      />
    )
  }
  const all = list.data ?? []
  const upcoming = all
    .filter((m) => new Date(m.ends_at).getTime() >= now)
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  const past = all.filter((m) => new Date(m.ends_at).getTime() < now)
  return (
    <div className="meetings">
      <PageHeader
        primary={
          canEdit && view === 'list' && !creating
            ? { label: t('Neue Versammlung'), onClick: () => setCreating(true) }
            : null
        }
      />
      <nav className="tabs" aria-label={t('Ansichten')}>
        <button
          type="button"
          className={`tab${view === 'list' ? ' active' : ''}`}
          aria-current={view === 'list' ? 'page' : undefined}
          onClick={() => show('list')}
        >
          {t('Versammlungen')}
        </button>
        <button
          type="button"
          className={`tab${view === 'kinds' ? ' active' : ''}`}
          aria-current={view === 'kinds' ? 'page' : undefined}
          onClick={() => show('kinds')}
        >
          {t('Arten und Fristen')}
        </button>
        <button
          type="button"
          className={`tab${view === 'book' ? ' active' : ''}`}
          aria-current={view === 'book' ? 'page' : undefined}
          onClick={() => show('book')}
        >
          {t('Beschlussbuch')}
        </button>
      </nav>
      {view === 'book' ? (
        <ResolutionBook
          base={base}
          canEdit={canEdit}
          kinds={kinds.data ?? []}
          assignOrg={assignOrg}
        />
      ) : view === 'kinds' ? (
        <KindsCard
          base={base}
          canEdit={canEdit}
          kinds={kinds.data}
          error={kinds.error}
          reload={kinds.reload}
        />
      ) : (
        <>
          {creating && (
            <NewMeeting
              base={base}
              kinds={(kinds.data ?? []).filter((k) => k.active)}
              onDone={async (created) => {
                setCreating(false)
                if (created) {
                  await list.reload()
                  detail.open(String(created.id))
                }
              }}
            />
          )}
          {list.error && <p role="alert">{list.error}</p>}
          <MeetingTable
            title={t('Anstehend')}
            empty={t('Keine anstehende Versammlung.')}
            rows={upcoming}
            open={(m) => detail.open(String(m.id))}
          />
          {past.length > 0 && (
            <MeetingTable
              title={t('Vergangen')}
              empty=""
              rows={past}
              open={(m) => detail.open(String(m.id))}
            />
          )}
        </>
      )}
    </div>
  )
}

function MeetingTable({
  title,
  empty,
  rows,
  open,
}: {
  title: string
  empty: string
  rows: Meeting[]
  open: (m: Meeting) => void
}) {
  const search = useRowSearch(
    rows,
    (m) => `${when(m)} ${m.title} ${m.kind_name} ${statusLabel(m.status)}`,
    title,
  )
  const sort = useRowSort(search.shown, {
    date: (m) => m.starts_at,
    title: (m) => m.title,
    kind: (m) => m.kind_name,
    status: (m) => statusLabel(m.status),
  })
  return (
    <section className="card">
      <h2>{title}</h2>
      {search.field}
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              {sort.head('date', t('Datum'))}
              {sort.head('title', t('Versammlung'))}
              {sort.head('kind', t('Art'))}
              {sort.head('status', t('Stand'))}
            </tr>
          </thead>
          <tbody>
            {sort.rows.map((m) => (
              <tr key={m.id}>
                <td>{when(m)}</td>
                <td>
                  <button type="button" className="link-button" onClick={() => open(m)}>
                    {m.title}
                  </button>
                </td>
                <td>{m.kind_name}</td>
                <td>
                  <span className={`badge${m.status === 'cancelled' ? ' badge-cancelled' : ''}`}>
                    {statusLabel(m.status)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function NewMeeting({
  base,
  kinds,
  onDone,
}: {
  base: string
  kinds: MeetingKind[]
  onDone: (created: Meeting | null) => void
}) {
  const [kind, setKind] = useState(kinds[0]?.id ?? 0)
  const [title, setTitle] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [location, setLocation] = useState('')
  const [fromLast, setFromLast] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useDraftGuard(!!(title || start || end || location))
  const chosen = kinds.find((k) => k.id === kind)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          const created = await meetingApi.create(base, {
            kind,
            title,
            starts_at: new Date(start).toISOString(),
            ends_at: new Date(end).toISOString(),
            location,
            agenda_from_last: fromLast,
          })
          onDone(created)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <h2>{t('Neue Versammlung')}</h2>
      <label className="field">
        <span>{t('Art')}</span>
        <select value={kind} onChange={(e) => setKind(Number(e.target.value))} required>
          {kinds.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}
            </option>
          ))}
        </select>
      </label>
      {chosen && (
        <p className="muted small">
          {t('Einladungsfrist: {n} Tage vor der Versammlung.', { n: chosen.invite_days })}
        </p>
      )}
      <label className="field">
        <span>{t('Titel')}</span>
        <input
          value={title}
          maxLength={200}
          placeholder={chosen?.name}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label className="field">
        <span>{t('Beginn')}</span>
        <input
          type="datetime-local"
          required
          value={start}
          onChange={(e) => {
            setStart(e.target.value)
            if (!end || end < e.target.value) setEnd(e.target.value)
          }}
        />
      </label>
      <label className="field">
        <span>{t('Ende')}</span>
        <input
          type="datetime-local"
          required
          value={end}
          min={start || undefined}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <PlaceField label={t('Ort')} value={location} onChange={setLocation} />
      <label className="checkbox">
        <input type="checkbox" checked={fromLast} onChange={(e) => setFromLast(e.target.checked)} />
        {t('Tagesordnung der letzten Versammlung dieser Art übernehmen')}
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button button-primary" disabled={busy || !kind}>
          {t('Anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
