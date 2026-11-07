// Versammlungen und Sitzungen (konzepte/versammlungen.md, Schritte V1–V5): Übersicht,
// Anlegen mit Termin, Tagesordnung, Einladung, Anwesenheit, Protokoll, Arten, Beschlussbuch.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { meetingApi } from '../../api/meetings.ts'
import type {
  AgendaItem,
  AttendanceList,
  AttendanceRow,
  AttendanceStatus,
  Confirmation,
  AgendaType,
  Meeting,
  MeetingBase,
  MeetingKind,
  MeetingStatus,
  MinutesItem,
  Resolution,
} from '../../api/meetings.ts'
import { saveBlob } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useDetailParam } from '../../components/detailParam.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { locale, t } from '../../i18n/index.ts'
import { PERM } from '../../api/orgs.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { MotionsCard } from './MotionsCard.tsx'
import { ResolutionBook } from './ResolutionBook.tsx'
import './meetings.css'

const ZONE = 'Europe/Berlin'

function statusLabel(status: MeetingStatus) {
  return {
    draft: t('in Vorbereitung'),
    invited: t('eingeladen'),
    held: t('durchgeführt'),
    minutes: t('Protokoll in Arbeit'),
    done: t('Protokoll freigegeben'),
    cancelled: t('abgesagt'),
  }[status]
}

function baseLabel(base: MeetingBase) {
  return {
    general: t('Mitgliederversammlung'),
    board: t('Vorstandssitzung'),
    committee: t('Gremium oder Ausschuss'),
  }[base]
}

function typeLabel(type: AgendaType) {
  return {
    report: t('Bericht'),
    resolution: t('Beschluss'),
    election: t('Wahl'),
    other: t('Sonstiges'),
  }[type]
}

const AGENDA_TYPES: AgendaType[] = ['report', 'resolution', 'election', 'other']

function when(m: Meeting) {
  return new Date(m.starts_at).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function day(value: string) {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString(locale(), { timeZone: 'UTC' })
}

/** Wert für ein datetime-local-Feld in der Zeitzone des Browsers */
function local(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function MeetingsPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('meetings') : !!activeDept?.meetings_enabled
  if (!enabled || !permissions.includes(PERM.meetingsView)) {
    return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
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
  const [creating, setCreating] = useState(false)
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
      <div className="page-heading">
        <h1>{t('Versammlungen')}</h1>
        {canEdit && view === 'list' && !creating && (
          <button className="button" onClick={() => setCreating(true)}>
            {t('Neue Versammlung')}
          </button>
        )}
      </div>
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
  return (
    <section className="card">
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Datum')}</th>
              <th>{t('Versammlung')}</th>
              <th>{t('Art')}</th>
              <th>{t('Stand')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
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
      <label>
        {t('Art')}
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
      <label>
        {t('Titel')}
        <input
          value={title}
          maxLength={200}
          placeholder={chosen?.name}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        {t('Beginn')}
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
      <label>
        {t('Ende')}
        <input
          type="datetime-local"
          required
          value={end}
          min={start || undefined}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <label>
        {t('Ort')}
        <input value={location} maxLength={200} onChange={(e) => setLocation(e.target.value)} />
      </label>
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

function MeetingDetail({
  base,
  id,
  kinds,
  onClose,
}: {
  base: string
  id: number
  kinds: MeetingKind[]
  onClose: () => void
}) {
  const loaded = useLoad(() => meetingApi.get(base, id), [base, id])
  const [error, setError] = useState('')
  const [today] = useState(() => new Date().toLocaleDateString('sv-SE', { timeZone: ZONE }))
  const meeting = loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!meeting) return <p>{t('Wird geladen …')}</p>
  const editable = meeting.can_edit && meeting.status !== 'cancelled'
  const late = meeting.status === 'draft' && meeting.invite_by < today
  const run = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <div className="meetings">
      <div className="page-heading">
        <h1>
          {meeting.title}
          <span className={`badge${meeting.status === 'cancelled' ? ' badge-cancelled' : ''}`}>
            {statusLabel(meeting.status)}
          </span>
        </h1>
        <button className="button button-ghost" onClick={onClose}>
          {t('Zurück zur Übersicht')}
        </button>
      </div>
      <p>
        {meeting.kind_name} · {when(meeting)}
        {meeting.location && ` · ${meeting.location}`}
      </p>
      {meeting.status === 'draft' && (
        <p className={late ? 'alert alert-error' : 'muted'} role={late ? 'alert' : undefined}>
          {late
            ? t(
                'Die Einladungsfrist ist verstrichen: Die Einladung hätte spätestens am {day} hinausgehen müssen.',
                { day: day(meeting.invite_by) },
              )
            : t('Einladung spätestens am {day} verschicken.', { day: day(meeting.invite_by) })}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <InvitationCard base={base} meeting={meeting} onChanged={loaded.reload} />
      {(meeting.motions ?? []).length > 0 && (
        <MotionsCard base={base} meeting={meeting} onChanged={loaded.reload} />
      )}
      <DetailsForm
        key={`d${meeting.version}`}
        base={base}
        meeting={meeting}
        kinds={kinds}
        editable={editable}
        onSaved={loaded.reload}
      />
      {MINUTES_STATES.includes(meeting.status) ? (
        <MinutesEditor
          key={`m${meeting.version}`}
          base={base}
          meeting={meeting}
          editable={meeting.can_edit && (meeting.status === 'held' || meeting.status === 'minutes')}
          onSaved={loaded.reload}
        />
      ) : (
        <AgendaEditor
          key={`a${meeting.version}`}
          base={base}
          meeting={meeting}
          editable={editable && (meeting.status === 'draft' || meeting.status === 'invited')}
          onSaved={loaded.reload}
        />
      )}
      {(meeting.status === 'minutes' || meeting.status === 'done') && (
        <ReleaseCard base={base} meeting={meeting} onChanged={loaded.reload} />
      )}
      {meeting.can_attendance && meeting.status !== 'cancelled' && (
        <AttendanceCard
          key={`t${meeting.status}`}
          base={base}
          meeting={meeting}
          onChanged={loaded.reload}
        />
      )}
      {meeting.can_edit && (
        <div className="button-row">
          {(meeting.status === 'draft' || meeting.status === 'invited') && (
            <button
              className="button button-ghost"
              onClick={() =>
                run(async () => {
                  const yes = await confirmDialog({
                    title: t('Versammlung absagen?'),
                    message: t('Der Termin bleibt im Kalender und wird als abgesagt gezeigt.'),
                    confirmLabel: t('Absagen'),
                  })
                  if (!yes) return
                  await meetingApi.update(base, meeting, { status: 'cancelled' })
                  await loaded.reload()
                })
              }
            >
              {t('Absagen')}
            </button>
          )}
          {(meeting.status === 'draft' || meeting.status === 'invited') && (
            <button
              className="button"
              onClick={() =>
                run(async () => {
                  const yes = await confirmDialog({
                    title: t('Versammlung als durchgeführt markieren?'),
                    message: t(
                      'Danach schreibst du das Protokoll. Die Tagesordnung lässt sich dann nicht mehr ändern.',
                    ),
                    confirmLabel: t('Durchgeführt'),
                  })
                  if (!yes) return
                  await meetingApi.update(base, meeting, { status: 'held' })
                  await loaded.reload()
                })
              }
            >
              {t('Als durchgeführt markieren')}
            </button>
          )}
          {meeting.status === 'cancelled' && (
            <button
              className="button button-ghost"
              onClick={() =>
                run(async () => {
                  await meetingApi.update(base, meeting, { status: 'draft' })
                  await loaded.reload()
                })
              }
            >
              {t('Wieder vorbereiten')}
            </button>
          )}
          {(meeting.status === 'draft' || meeting.status === 'cancelled') && (
            <button
              className="button button-danger"
              onClick={() =>
                run(async () => {
                  const yes = await confirmDialog({
                    title: t('Versammlung löschen?'),
                    message: t('Termin und Tagesordnung werden ebenfalls gelöscht.'),
                    confirmLabel: t('Löschen'),
                  })
                  if (!yes) return
                  await meetingApi.remove(base, meeting.id)
                  onClose()
                })
              }
            >
              {t('Löschen')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function DetailsForm({
  base,
  meeting,
  kinds,
  editable,
  onSaved,
}: {
  base: string
  meeting: Meeting
  kinds: MeetingKind[]
  editable: boolean
  onSaved: () => Promise<void>
}) {
  const initial = {
    kind: meeting.kind,
    title: meeting.title,
    start: local(meeting.starts_at),
    end: local(meeting.ends_at),
    location: meeting.location,
    address: meeting.address,
    chair: meeting.chair ?? '',
    minute_taker: meeting.minute_taker ?? '',
    note: meeting.note ?? '',
  }
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = JSON.stringify(form) !== JSON.stringify(initial)
  useDraftGuard(dirty, () => setForm(initial))
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value })
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await meetingApi.update(base, meeting, {
            kind: Number(form.kind),
            title: form.title,
            starts_at: new Date(form.start).toISOString(),
            ends_at: new Date(form.end).toISOString(),
            location: form.location,
            address: form.address,
            chair: form.chair,
            minute_taker: form.minute_taker,
            note: form.note,
          })
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Angaben')}</h2>
      <fieldset disabled={!editable} className="stack">
        <label>
          {t('Art')}
          <select value={form.kind} onChange={set('kind')}>
            {kinds
              .filter((k) => k.active || k.id === meeting.kind)
              .map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          {t('Titel')}
          <input value={form.title} maxLength={200} required onChange={set('title')} />
        </label>
        <label>
          {t('Beginn')}
          <input type="datetime-local" required value={form.start} onChange={set('start')} />
        </label>
        <label>
          {t('Ende')}
          <input
            type="datetime-local"
            required
            value={form.end}
            min={form.start || undefined}
            onChange={set('end')}
          />
        </label>
        <label>
          {t('Ort')}
          <input value={form.location} maxLength={200} onChange={set('location')} />
        </label>
        <label>
          {t('Anschrift')}
          <input value={form.address} maxLength={300} onChange={set('address')} />
        </label>
        <label>
          {t('Leitung')}
          <input value={form.chair} maxLength={200} onChange={set('chair')} />
        </label>
        <label>
          {t('Protokollführung')}
          <input value={form.minute_taker} maxLength={200} onChange={set('minute_taker')} />
        </label>
        <label>
          {t('Notiz (nur für die Verwaltung)')}
          <textarea value={form.note} maxLength={5000} rows={3} onChange={set('note')} />
        </label>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {editable && (
        <div className="button-row">
          <button className="button button-primary" disabled={busy || !dirty}>
            {t('Speichern')}
          </button>
        </div>
      )}
    </form>
  )
}

function AgendaEditor({
  base,
  meeting,
  editable,
  onSaved,
}: {
  base: string
  meeting: Meeting
  editable: boolean
  onSaved: () => Promise<void>
}) {
  const initial: AgendaItem[] = (meeting.agenda ?? []).map((a) => ({
    id: a.id,
    title: a.title,
    description: a.description,
    type: a.type,
  }))
  const [items, setItems] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = JSON.stringify(items) !== JSON.stringify(initial)
  useDraftGuard(dirty, () => setItems(initial))
  const change = (index: number, patch: Partial<AgendaItem>) =>
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  const move = (index: number, by: number) => {
    const next = [...items]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    setItems(next)
  }
  if (!editable) {
    return (
      <section className="card">
        <h2>{t('Tagesordnung')}</h2>
        <ol className="agenda-list">
          {initial.map((item) => (
            <li key={item.id ?? item.title}>
              <strong>{item.title}</strong>
              {item.description && <p className="muted">{item.description}</p>}
            </li>
          ))}
        </ol>
      </section>
    )
  }
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await meetingApi.saveAgenda(base, meeting, items)
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Tagesordnung')}</h2>
      <ol className="agenda-edit">
        {items.map((item, index) => (
          <li key={item.id ?? `neu-${index}`} className="agenda-row">
            <div className="agenda-fields">
              <label>
                {t('TOP {n}', { n: index + 1 })}
                <input
                  value={item.title}
                  maxLength={300}
                  required
                  onChange={(e) => change(index, { title: e.target.value })}
                />
              </label>
              <label>
                {t('Art des Punkts')}
                <select
                  value={item.type}
                  onChange={(e) => change(index, { type: e.target.value as AgendaType })}
                >
                  {AGENDA_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {typeLabel(type)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t('Erläuterung')}
                <textarea
                  value={item.description}
                  maxLength={5000}
                  rows={2}
                  onChange={(e) => change(index, { description: e.target.value })}
                />
              </label>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                disabled={index === 0}
                aria-label={t('TOP {n} nach oben', { n: index + 1 })}
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="button button-ghost"
                disabled={index === items.length - 1}
                aria-label={t('TOP {n} nach unten', { n: index + 1 })}
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setItems(items.filter((_, i) => i !== index))}
              >
                {t('Entfernen')}
              </button>
            </div>
          </li>
        ))}
      </ol>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => setItems([...items, { title: '', description: '', type: 'other' }])}
        >
          {t('Punkt hinzufügen')}
        </button>
        <button className="button button-primary" disabled={busy || !dirty}>
          {t('Tagesordnung speichern')}
        </button>
      </div>
    </form>
  )
}

const BASES: MeetingBase[] = ['general', 'board', 'committee']

function KindsCard({
  base,
  canEdit,
  kinds,
  error,
  reload,
}: {
  base: string
  canEdit: boolean
  kinds: MeetingKind[] | null
  error: string | null
  reload: () => Promise<void>
}) {
  const [editing, setEditing] = useState<MeetingKind | 'new' | null>(null)
  const [message, setMessage] = useState('')
  return (
    <section className="card">
      <h2>{t('Arten und Fristen')}</h2>
      <p className="muted small">
        {t(
          'Die Art legt die Voreinstellungen fest, zum Beispiel die Einladungsfrist aus der Satzung. HUBIplan warnt, wenn eine Einladung zu spät hinausgeht.',
        )}
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="alert">{message}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>{t('Name')}</th>
            <th>{t('Grundtyp')}</th>
            <th className="num">{t('Frist (Tage)')}</th>
            <th>{t('Protokoll sehen')}</th>
            {canEdit && <th className="actions">{t('Aktionen')}</th>}
          </tr>
        </thead>
        <tbody>
          {(kinds ?? []).map((k) => (
            <tr key={k.id}>
              <td>
                {k.name}
                {!k.active && <span className="badge">{t('abgeschaltet')}</span>}
              </td>
              <td>{baseLabel(k.base)}</td>
              <td className="num">{k.invite_days}</td>
              <td>
                {k.minutes_for === 'voters'
                  ? t('auch alle Stimmberechtigten')
                  : t('nur Rollen mit Leserecht')}
              </td>
              {canEdit && (
                <td className="actions">
                  <div className="button-row">
                    <button className="button button-ghost" onClick={() => setEditing(k)}>
                      {t('Bearbeiten')}
                    </button>
                    {!k.used && (
                      <button
                        className="button button-ghost"
                        onClick={async () => {
                          setMessage('')
                          const yes = await confirmDialog({
                            title: t('Art „{name}“ löschen?', { name: k.name }),
                            confirmLabel: t('Löschen'),
                          })
                          if (!yes) return
                          try {
                            await meetingApi.removeKind(base, k.id)
                            await reload()
                          } catch (err) {
                            setMessage(errorMessage(err))
                          }
                        }}
                      >
                        {t('Löschen')}
                      </button>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {canEdit && !editing && (
        <div className="button-row">
          <button className="button" onClick={() => setEditing('new')}>
            {t('Art hinzufügen')}
          </button>
        </div>
      )}
      {editing && (
        <KindForm
          key={editing === 'new' ? 'new' : editing.id}
          base={base}
          kind={editing === 'new' ? null : editing}
          onDone={async (saved) => {
            setEditing(null)
            if (saved) await reload()
          }}
        />
      )}
    </section>
  )
}

function KindForm({
  base,
  kind,
  onDone,
}: {
  base: string
  kind: MeetingKind | null
  onDone: (saved: boolean) => void
}) {
  const initial = {
    name: kind?.name ?? '',
    base: kind?.base ?? ('general' as MeetingBase),
    invite_days: String(kind?.invite_days ?? 14),
    invite_form: kind?.invite_form ?? 'mail',
    minutes_for: kind?.minutes_for ?? 'board',
    quorum_percent: kind?.quorum_percent ? String(kind.quorum_percent) : '',
    proxies_allowed: kind?.proxies_allowed ?? false,
    motion_days: kind ? (kind.motion_days === null ? '' : String(kind.motion_days)) : '7',
    active: kind?.active ?? true,
  }
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useDraftGuard(JSON.stringify(form) !== JSON.stringify(initial))
  return (
    <form
      className="stack kind-form"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        const data = {
          ...form,
          invite_days: Number(form.invite_days),
          quorum_percent: form.quorum_percent ? Number(form.quorum_percent) : null,
          motion_days: form.motion_days === '' ? null : Number(form.motion_days),
        }
        try {
          if (kind) await meetingApi.updateKind(base, kind.id, data)
          else await meetingApi.createKind(base, data)
          onDone(true)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <h3>{kind ? t('Art bearbeiten') : t('Neue Art')}</h3>
      <label>
        {t('Name')}
        <input
          value={form.name}
          maxLength={100}
          required
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </label>
      <label>
        {t('Grundtyp')}
        <select
          value={form.base}
          onChange={(e) => setForm({ ...form, base: e.target.value as MeetingBase })}
        >
          {BASES.map((b) => (
            <option key={b} value={b}>
              {baseLabel(b)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('Einladungsfrist in Tagen')}
        <input
          type="number"
          min={0}
          max={365}
          required
          value={form.invite_days}
          onChange={(e) => setForm({ ...form, invite_days: e.target.value })}
        />
      </label>
      <label>
        {t('Einladung')}
        <select
          value={form.invite_form}
          onChange={(e) =>
            setForm({ ...form, invite_form: e.target.value as MeetingKind['invite_form'] })
          }
        >
          <option value="mail">{t('E-Mail, sonst Brief')}</option>
          <option value="letter">{t('Brief an alle')}</option>
        </select>
      </label>
      <label>
        {t('Beschlussfähig ab (Prozent der Stimmberechtigten, leer: immer)')}
        <input
          type="number"
          min={1}
          max={100}
          value={form.quorum_percent}
          onChange={(e) => setForm({ ...form, quorum_percent: e.target.value })}
        />
      </label>
      <label>
        {t('Protokoll sehen')}
        <select
          value={form.minutes_for}
          onChange={(e) =>
            setForm({ ...form, minutes_for: e.target.value as MeetingKind['minutes_for'] })
          }
        >
          <option value="board">{t('nur Rollen mit Leserecht')}</option>
          <option value="voters">{t('auch alle Stimmberechtigten')}</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.proxies_allowed}
          onChange={(e) => setForm({ ...form, proxies_allowed: e.target.checked })}
        />
        {t('Vertretung mit Vollmacht erlaubt')}
      </label>
      <label>
        {t('Anträge von Mitgliedern bis Tage vorher (leer: keine Anträge)')}
        <input
          type="number"
          min={0}
          max={90}
          value={form.motion_days}
          onChange={(e) => setForm({ ...form, motion_days: e.target.value })}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.active}
          onChange={(e) => setForm({ ...form, active: e.target.checked })}
        />
        {t('Für neue Versammlungen wählbar')}
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function InvitationCard({
  base,
  meeting,
  onChanged,
}: {
  base: string
  meeting: Meeting
  onChanged: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (meeting.status === 'cancelled') return null
  const invitedLate =
    !!meeting.invited_at &&
    new Date(meeting.invited_at).toLocaleDateString('sv-SE', { timeZone: ZONE }) > meeting.invite_by
  return (
    <section className="card stack">
      <h2>{t('Einladung')}</h2>
      {meeting.invited_at ? (
        <p className={invitedLate ? 'alert alert-error' : undefined}>
          {t('Eingeladen am {day}.', {
            day: new Date(meeting.invited_at).toLocaleDateString(locale(), { timeZone: ZONE }),
          })}
          {invitedLate && ' ' + t('Das war nach dem letzten Tag der Einladungsfrist.')}
        </p>
      ) : meeting.circular && meeting.circular_status === 'draft' ? (
        <p>
          {t(
            'Der Entwurf der Einladung liegt bei den Rundschreiben. Dort prüfst du Empfänger und Text und verschickst sie.',
          )}
        </p>
      ) : (
        <p className="muted">
          {t(
            'Die Einladung entsteht als Rundschreiben mit Tagesordnung an die Stimmberechtigten. Du prüfst es dort und verschickst es selbst.',
          )}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        {meeting.circular ? (
          <Link className="button" to={`/rundschreiben/${meeting.circular}`}>
            {t('Rundschreiben öffnen')}
          </Link>
        ) : (
          meeting.status === 'draft' &&
          meeting.can_invite && (
            <button
              className="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                setError('')
                try {
                  await meetingApi.prepareInvitation(base, meeting)
                  await onChanged()
                } catch (err) {
                  setError(errorMessage(err))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Einladung vorbereiten')}
            </button>
          )
        )}
      </div>
      {meeting.status === 'draft' && meeting.can_edit && !meeting.can_invite && (
        <p className="muted small">
          {t('Für die Einladung ist zusätzlich das Recht nötig, Rundschreiben zu versenden.')}
        </p>
      )}
    </section>
  )
}

const ATTENDANCE: AttendanceStatus[] = ['present', 'delegate', 'excused', 'represented']

function attendanceLabel(status: AttendanceStatus) {
  if (status === 'present') return t('Anwesend')
  if (status === 'excused') return t('Entschuldigt')
  if (status === 'delegate') return t('Durch Vertreter')
  return t('Vertreten')
}

/** Vertreter eines Organisationsmitglieds wählen: Ansprechpartner oder freier Name (J4). */
function DelegatePicker({
  row,
  busy,
  onPick,
}: {
  row: AttendanceRow
  busy: boolean
  onPick: (data: { delegate?: number; delegate_name?: string }) => void
}) {
  const [name, setName] = useState('')
  const delegates = row.delegates ?? []
  return (
    <div className="stack">
      {delegates.length > 0 && (
        <label className="field">
          <span>{t('Vertreter')}</span>
          <select
            value=""
            disabled={busy}
            onChange={(e) => {
              if (e.target.value) onPick({ delegate: Number(e.target.value) })
            }}
          >
            <option value="">{t('Bitte wählen')}</option>
            {delegates.map((d) => (
              <option key={d.id} value={d.id}>
                {d.function ? `${d.name} (${d.function})` : d.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <form
        className="button-row"
        onSubmit={(e) => {
          e.preventDefault()
          if (name.trim()) onPick({ delegate_name: name.trim() })
        }}
      >
        <label className="field">
          <span>
            {delegates.length > 0 ? t('Oder anderer Vertreter') : t('Name des Vertreters')}
          </span>
          <input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="button" type="submit" disabled={busy || !name.trim()}>
          {t('Eintragen')}
        </button>
      </form>
    </div>
  )
}

function AttendanceCard({
  base,
  meeting,
  onChanged,
}: {
  base: string
  meeting: Meeting
  onChanged: () => Promise<void>
}) {
  const loaded = useLoad(() => meetingApi.attendance(base, meeting.id), [base, meeting.id])
  const [list, setList] = useState<AttendanceList | null>(null)
  const [query, setQuery] = useState('')
  const [guest, setGuest] = useState('')
  const [proxyFor, setProxyFor] = useState<number | null>(null)
  const [delegateFor, setDelegateFor] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const data = list ?? loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!data) return <p>{t('Wird geladen …')}</p>
  const send = async (action: () => Promise<AttendanceList | unknown>, reload = false) => {
    setBusy(true)
    setError('')
    try {
      const result = await action()
      if (reload) setList(await meetingApi.attendance(base, meeting.id))
      else setList(result as AttendanceList)
      // Im Protokoll: Bestätigungen fallen weg, der Stand der Versammlung ändert sich
      if (meeting.chair_confirmed || meeting.taker_confirmed) await onChanged()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  const mark = (row: AttendanceRow, status: AttendanceStatus, holder?: number) =>
    send(() =>
      meetingApi.markAttendance(
        base,
        meeting.id,
        row.membership
          ? { membership: row.membership, status, represented_by: holder ?? null }
          : { name: row.name, status },
      ),
    )
  const holders = data.rows.filter((r) => r.voter && r.status === 'present' && r.id)
  const names = new Map(data.rows.filter((r) => r.id).map((r) => [r.id, r.name]))
  const needle = query.trim().toLowerCase()
  const shown = needle ? data.rows.filter((r) => r.name.toLowerCase().includes(needle)) : data.rows
  const counted = data.present + data.represented
  return (
    <section className="card stack attendance">
      <h2>{t('Anwesenheit')}</h2>
      <p>
        {t(
          '{present} von {voters} Stimmberechtigten anwesend, {represented} vertreten, {guests} Gäste.',
          {
            present: data.present,
            voters: data.voters,
            represented: data.represented,
            guests: data.guests,
          },
        )}
      </p>
      {data.quorum.rule ? (
        <p className={data.quorum.reached ? undefined : 'alert alert-error'} role="status">
          {data.quorum.reached
            ? t('Beschlussfähig: {counted} Stimmen, nötig sind {needed}.', {
                counted,
                needed: data.quorum.needed,
              })
            : t('Noch nicht beschlussfähig: {counted} Stimmen, nötig sind {needed}.', {
                counted,
                needed: data.quorum.needed,
              })}
        </p>
      ) : (
        <p className="muted">
          {t('Für diese Art ist keine Mindestzahl für die Beschlussfähigkeit festgelegt.')}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {data.rows.length > 10 && (
        <label className="field">
          <span>{t('Name suchen')}</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      )}
      {data.rows.length === 0 ? (
        <p className="muted">{t('Es gibt keine Stimmberechtigten für diese Versammlung.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Anwesenheit')}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.membership ? `m${row.membership}` : `g${row.id}`}>
                <td>
                  {row.name}
                  {!row.voter && <span className="badge">{t('Gast')}</span>}
                  {row.status === 'delegate' && row.delegate_name && (
                    <div className="muted small">
                      {t('anwesend durch {name}', { name: row.delegate_name })}
                    </div>
                  )}
                  {(row.also_represents ?? []).length > 0 && (
                    <div className="muted small">
                      {t('vertritt zusätzlich: {x}', { x: (row.also_represents ?? []).join(', ') })}
                    </div>
                  )}
                  {row.status === 'represented' && row.represented_by && (
                    <div className="muted small">
                      {t('vertreten durch {name}', { name: names.get(row.represented_by) ?? '' })}
                    </div>
                  )}
                </td>
                <td>
                  {data.editable ? (
                    <div className="attendance-cell">
                      <div className="segmented" role="group" aria-label={row.name}>
                        {ATTENDANCE.filter((s) =>
                          // Organisationen: „Durch Vertreter“ statt Anwesend und Vollmacht
                          row.kind === 'organization'
                            ? s !== 'present' && s !== 'represented'
                            : s !== 'delegate' &&
                              (s !== 'represented' || (data.proxies_allowed && row.voter)),
                        ).map((s) => (
                          <button
                            key={s}
                            type="button"
                            className={`button button-ghost${row.status === s ? ' is-active' : ''}`}
                            aria-pressed={row.status === s}
                            disabled={busy}
                            onClick={() => {
                              if (s === 'represented') {
                                setDelegateFor(null)
                                setProxyFor(row.membership)
                              } else if (s === 'delegate') {
                                setProxyFor(null)
                                setDelegateFor(row.membership)
                              } else {
                                setProxyFor(null)
                                setDelegateFor(null)
                                void mark(row, s)
                              }
                            }}
                          >
                            {attendanceLabel(s)}
                          </button>
                        ))}
                        {row.id && !row.voter && (
                          <button
                            type="button"
                            className="button button-ghost"
                            disabled={busy}
                            onClick={() =>
                              void send(
                                () => meetingApi.removeAttendance(base, meeting.id, row.id!),
                                true,
                              )
                            }
                          >
                            {t('Entfernen')}
                          </button>
                        )}
                      </div>
                      {delegateFor !== null && delegateFor === row.membership && (
                        <DelegatePicker
                          row={row}
                          busy={busy}
                          onPick={async (choice) => {
                            const done = await send(() =>
                              meetingApi.markAttendance(base, meeting.id, {
                                membership: row.membership,
                                status: 'delegate',
                                ...choice,
                              }),
                            )
                            if (done) setDelegateFor(null)
                          }}
                        />
                      )}
                      {proxyFor !== null && proxyFor === row.membership && (
                        <label className="field">
                          <span>{t('Vertreten durch')}</span>
                          <select
                            value=""
                            onChange={async (e) => {
                              if (!e.target.value) return
                              if (await mark(row, 'represented', Number(e.target.value)))
                                setProxyFor(null)
                            }}
                          >
                            <option value="">{t('Bitte wählen')}</option>
                            {holders
                              .filter((h) => h.membership !== row.membership)
                              .map((h) => (
                                <option key={h.id!} value={h.id!}>
                                  {h.name}
                                </option>
                              ))}
                          </select>
                        </label>
                      )}
                    </div>
                  ) : row.status ? (
                    attendanceLabel(row.status)
                  ) : (
                    <span className="muted">{t('nicht erfasst')}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.editable && (
        <form
          className="button-row"
          onSubmit={async (e) => {
            e.preventDefault()
            const name = guest.trim()
            if (!name) return
            if (
              await send(() =>
                meetingApi.markAttendance(base, meeting.id, { name, status: 'present' }),
              )
            )
              setGuest('')
          }}
        >
          <label className="field">
            <span>{t('Gast ohne Stimmrecht')}</span>
            <input value={guest} maxLength={200} onChange={(e) => setGuest(e.target.value)} />
          </label>
          <button className="button" type="submit" disabled={busy || !guest.trim()}>
            {t('Gast eintragen')}
          </button>
        </form>
      )}
    </section>
  )
}

const MINUTES_STATES: MeetingStatus[] = ['held', 'minutes', 'done']

function emptyResolution(kind: Resolution['kind']): Resolution {
  return {
    kind,
    text: '',
    votes_yes: null,
    votes_no: null,
    votes_abstain: null,
    unanimous: false,
    result: 'accepted',
    office: '',
    elected_name: '',
  }
}

function resultLabel(r: Resolution) {
  if (r.kind === 'election') return r.result === 'accepted' ? t('gewählt') : t('nicht gewählt')
  return r.result === 'accepted' ? t('angenommen') : t('abgelehnt')
}

function voteSummary(r: Resolution) {
  if (r.unanimous) return t('einstimmig')
  if (r.votes_yes === null && r.votes_no === null && r.votes_abstain === null) return ''
  return t('Ja {yes}, Nein {no}, Enthaltung {abstain}', {
    yes: r.votes_yes ?? 0,
    no: r.votes_no ?? 0,
    abstain: r.votes_abstain ?? 0,
  })
}

function count(value: string): number | null {
  if (value === '') return null
  const n = Number(value)
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null
}

function MinutesEditor({
  base,
  meeting,
  editable,
  onSaved,
}: {
  base: string
  meeting: Meeting
  editable: boolean
  onSaved: () => Promise<void>
}) {
  const agenda = meeting.agenda ?? []
  const initial: MinutesItem[] = agenda.map((a) => ({
    id: a.id!,
    minutes: a.minutes ?? '',
    resolutions: (a.resolutions ?? []).map((r) => ({ ...r })),
  }))
  const [items, setItems] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dirty = JSON.stringify(items) !== JSON.stringify(initial)
  useDraftGuard(dirty, () => setItems(initial))
  const change = (index: number, patch: Partial<MinutesItem>) =>
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  const changeResolution = (index: number, r: number, patch: Partial<Resolution>) =>
    change(index, {
      resolutions: items[index].resolutions.map((x, j) => (j === r ? { ...x, ...patch } : x)),
    })
  if (!editable) {
    return (
      <section className="card stack">
        <h2>{t('Protokoll der Versammlung')}</h2>
        <ol className="agenda-list">
          {agenda.map((a) => (
            <li key={a.id!}>
              <strong>{a.title}</strong>
              {a.minutes && <p className="minutes-text">{a.minutes}</p>}
              {(a.resolutions ?? []).map((r) => (
                <p key={r.id!} className="resolution">
                  <strong>
                    {r.kind === 'election'
                      ? t('Wahl {office}: {name}', { office: r.office, name: r.elected_name })
                      : t('Beschluss')}
                  </strong>
                  {r.kind === 'resolution' && <> {r.text}</>} (
                  {[voteSummary(r), resultLabel(r)].filter(Boolean).join(', ')})
                </p>
              ))}
            </li>
          ))}
        </ol>
      </section>
    )
  }
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await meetingApi.saveMinutes(base, meeting, items)
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Protokoll der Versammlung')}</h2>
      <p className="muted">
        {t(
          'Halte je Tagesordnungspunkt fest, was besprochen wurde, und trage Beschlüsse und Wahlen mit dem Ergebnis ein.',
        )}
      </p>
      <ol className="agenda-edit">
        {items.map((item, index) => (
          <li key={item.id} className="agenda-row">
            <h3>{agenda[index].title}</h3>
            <label>
              {t('Protokoll zu TOP {n}', { n: index + 1 })}
              <textarea
                value={item.minutes}
                rows={4}
                maxLength={50000}
                onChange={(e) => change(index, { minutes: e.target.value })}
              />
            </label>
            {item.resolutions.map((r, j) => (
              <fieldset key={r.id ?? `neu-${j}`} className="resolution-edit">
                <legend>{r.kind === 'election' ? t('Wahl') : t('Beschluss')}</legend>
                {r.kind === 'election' ? (
                  <div className="agenda-fields">
                    <label>
                      {t('Amt')}
                      <input
                        value={r.office}
                        maxLength={200}
                        required
                        onChange={(e) => changeResolution(index, j, { office: e.target.value })}
                      />
                    </label>
                    <label>
                      {t('Gewählt')}
                      <input
                        value={r.elected_name}
                        maxLength={200}
                        required
                        onChange={(e) =>
                          changeResolution(index, j, {
                            elected_name: e.target.value,
                            elected: null,
                          })
                        }
                      />
                    </label>
                  </div>
                ) : (
                  <label>
                    {t('Beschlusstext')}
                    <textarea
                      value={r.text}
                      rows={2}
                      maxLength={5000}
                      required
                      onChange={(e) => changeResolution(index, j, { text: e.target.value })}
                    />
                  </label>
                )}
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={r.unanimous}
                    onChange={(e) =>
                      changeResolution(index, j, {
                        unanimous: e.target.checked,
                        ...(e.target.checked ? { result: 'accepted' as const } : {}),
                      })
                    }
                  />
                  {t('einstimmig')}
                </label>
                {!r.unanimous && (
                  <div className="vote-fields">
                    <label>
                      {t('Ja')}
                      <input
                        type="number"
                        min={0}
                        value={r.votes_yes ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_yes: count(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      {t('Nein')}
                      <input
                        type="number"
                        min={0}
                        value={r.votes_no ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_no: count(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      {t('Enthaltung')}
                      <input
                        type="number"
                        min={0}
                        value={r.votes_abstain ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_abstain: count(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      {t('Ergebnis')}
                      <select
                        value={r.result}
                        onChange={(e) =>
                          changeResolution(index, j, {
                            result: e.target.value as Resolution['result'],
                          })
                        }
                      >
                        <option value="accepted">
                          {r.kind === 'election' ? t('gewählt') : t('angenommen')}
                        </option>
                        <option value="rejected">
                          {r.kind === 'election' ? t('nicht gewählt') : t('abgelehnt')}
                        </option>
                      </select>
                    </label>
                  </div>
                )}
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      change(index, {
                        resolutions: item.resolutions.filter((_, k) => k !== j),
                      })
                    }
                  >
                    {t('Entfernen')}
                  </button>
                </div>
              </fieldset>
            ))}
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  change(index, {
                    resolutions: [...item.resolutions, emptyResolution('resolution')],
                  })
                }
              >
                {t('Beschluss hinzufügen')}
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  change(index, { resolutions: [...item.resolutions, emptyResolution('election')] })
                }
              >
                {t('Wahl hinzufügen')}
              </button>
            </div>
          </li>
        ))}
      </ol>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button button-primary" disabled={busy || !dirty}>
          {t('Protokoll speichern')}
        </button>
      </div>
    </form>
  )
}

function ReleaseCard({
  base,
  meeting,
  onChanged,
}: {
  base: string
  meeting: Meeting
  onChanged: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const dayOf = (value: string) => new Date(value).toLocaleDateString(locale(), { timeZone: ZONE })
  const done = meeting.status === 'done'
  const roles: {
    role: 'chair' | 'taker'
    label: string
    ask: string
    info?: Confirmation | null
  }[] = [
    {
      role: 'chair',
      label: t('Leitung'),
      ask: t('Als Leitung bestätigen'),
      info: meeting.chair_confirmed,
    },
    {
      role: 'taker',
      label: t('Protokollführung'),
      ask: t('Als Protokollführung bestätigen'),
      info: meeting.taker_confirmed,
    },
  ]
  return (
    <section className="card stack">
      <h2>{t('Freigabe des Protokolls')}</h2>
      {done ? (
        <p>
          {t('Freigegeben am {day}. Das Protokoll lässt sich nicht mehr ändern.', {
            day: meeting.released_at ? dayOf(meeting.released_at) : '',
          })}
          {meeting.minutes_document
            ? ' ' + t('Es liegt in den Dokumenten im Ordner „Protokolle“.')
            : ''}
        </p>
      ) : (
        <p className="muted">
          {t(
            'Leitung und Protokollführung bestätigen das Protokoll. Mit der zweiten Bestätigung ist es freigegeben, die Beschlüsse bekommen ihre Nummer, und es lässt sich nicht mehr ändern. Jede Änderung am Protokoll oder an der Anwesenheit hebt die Bestätigungen auf.',
          )}
        </p>
      )}
      <ul className="confirm-list">
        {roles.map((r) => (
          <li key={r.role}>
            <strong>{r.label}:</strong>{' '}
            {r.info
              ? t('bestätigt von {name} am {day}', { name: r.info.name, day: dayOf(r.info.at) })
              : t('noch nicht bestätigt')}
            {!done && !r.info && meeting.can_edit && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const yes = await confirmDialog({
                      title: r.ask + '?',
                      message: t(
                        'Bitte nur bestätigen, wenn du das Protokoll gelesen hast und es stimmt.',
                      ),
                      confirmLabel: t('Bestätigen'),
                    })
                    if (!yes) return
                    await meetingApi.confirmMinutes(base, meeting, r.role)
                    await onChanged()
                  })
                }
              >
                {r.ask}
              </button>
            )}
          </li>
        ))}
      </ul>
      {meeting.minutes_sha256 && (
        <p className="muted small">
          {t('Prüfsumme (SHA-256): {hash}', { hash: meeting.minutes_sha256 })}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() =>
            run(async () =>
              saveBlob(
                await meetingApi.minutesPdf(base, meeting),
                done ? 'protokoll.pdf' : 'protokoll-entwurf.pdf',
              ),
            )
          }
        >
          {done ? t('Protokoll als PDF') : t('Vorschau als PDF')}
        </button>
      </div>
    </section>
  )
}
