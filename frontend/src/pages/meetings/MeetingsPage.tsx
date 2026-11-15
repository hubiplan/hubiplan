// Versammlungen und Sitzungen (konzepte/versammlungen.md, Schritte V1–V7): Übersicht,
// Anlegen mit Termin, Tagesordnung, Einladung, Anwesenheit, Protokoll, Arten, Beschlussbuch.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { berlin } from '../../components/calendar/time.ts'
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
import { ApiError, saveBlob } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useDetailParam } from '../../components/detailParam.ts'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { flushAllForms, useDraftGuard } from '../../components/leaveGuard.ts'
import { locale, t } from '../../i18n/index.ts'
import { PERM } from '../../api/orgs.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { HowTo, Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { meetingInviteChecks } from '../../learning/checks.ts'
import { MotionsCard } from './MotionsCard.tsx'
import { LiveCard } from './LiveCard.tsx'
import { LIVE_STATES } from './live.ts'
import { ResolutionBook } from './ResolutionBook.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading, SaveStatus } from '../../components/ui.tsx'
import './meetings.css'
import { GripIcon } from '../../components/Sortable.tsx'
import {
  addSub,
  agendaNumbers,
  attach,
  blockEnd,
  canMove,
  moveRow,
  normalize,
  parentIndex,
  removeRow,
  dropBlock,
} from './agendaTree.ts'
import type { AgendaRow, DropTarget } from './agendaTree.ts'
import { PlaceField } from '../../components/PlaceField.tsx'

const ZONE = 'Europe/Berlin'

/**
 * Autospeichern in der Versammlung: Angaben, Tagesordnung und Protokoll speichern einzeln,
 * jede Antwort bringt eine neue Fassung (`version`). Die Formulare holen sich darum die
 * jeweils neueste Versammlung hier ab und melden ihre Antwort zurück, ohne dass die
 * anderen Formulare neu aufgebaut werden (Eingaben und Fokus bleiben erhalten).
 */
type Sync = {
  current: () => Meeting
  stored: (meeting: Meeting) => void
}

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
  const newest = useRef<Meeting | null>(null)
  const loaded = useLoad(async () => {
    const m = await meetingApi.get(base, id)
    newest.current = m
    return m
  }, [base, id])
  // Zählt hoch, wenn die Versammlung von anderer Stelle geändert wurde (Einladung, Anträge,
  // Abstimmung, Status): dann bauen sich die Formulare aus dem neuen Stand neu auf
  const [epoch, setEpoch] = useState(0)
  const [error, setError] = useState('')
  const [today] = useState(() => new Date().toLocaleDateString('sv-SE', { timeZone: ZONE }))
  const meeting = loaded.data
  const setData = loaded.setData
  const reload = loaded.reload
  const sync: Sync = useMemo(
    () => ({
      current: () => newest.current!,
      stored: (m) => {
        newest.current = m
        setData(m)
      },
    }),
    [setData],
  )
  const refresh = async () => {
    await reload()
    // Noch nicht Gespeichertes mit der neuen Fassung nachholen, bevor neu aufgebaut wird
    await flushAllForms()
    setEpoch((e) => e + 1)
  }
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!meeting) return <Loading />
  const editable = meeting.can_edit && meeting.status !== 'cancelled'
  const late = meeting.status === 'draft' && meeting.invite_by < today
  const run = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      // Erst alles speichern: der Statuswechsel braucht die neueste Fassung
      if (!(await flushAllForms())) return
      await action()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <div className="meetings">
      <PageHeader
        title={meeting.title}
        status={
          <span className={`badge${meeting.status === 'cancelled' ? ' badge-cancelled' : ''}`}>
            {statusLabel(meeting.status)}
          </span>
        }
        onBack={onClose}
      />
      <p>
        {meeting.kind_name} · {when(meeting)}
        {meeting.location && ` · ${meeting.location}`}
        {' · '}
        <Link to={`/termine?termin=${meeting.event}&datum=${berlin(meeting.starts_at).date}`}>
          {t('Termin im Kalender')}
        </Link>
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
      <InvitationCard base={base} meeting={meeting} onChanged={refresh} />
      {(meeting.motions ?? []).length > 0 && (
        <MotionsCard base={base} meeting={meeting} onChanged={refresh} />
      )}
      <DetailsForm
        key={`d${epoch}`}
        base={base}
        meeting={meeting}
        kinds={kinds}
        editable={editable}
        sync={sync}
      />
      {MINUTES_STATES.includes(meeting.status) ? (
        <MinutesEditor
          key={`m${epoch}`}
          base={base}
          meeting={meeting}
          editable={meeting.can_edit && (meeting.status === 'held' || meeting.status === 'minutes')}
          sync={sync}
        />
      ) : (
        <AgendaEditor
          key={`a${epoch}`}
          base={base}
          meeting={meeting}
          editable={editable && (meeting.status === 'draft' || meeting.status === 'invited')}
          sync={sync}
        />
      )}
      {(meeting.status === 'minutes' || meeting.status === 'done') && (
        <ReleaseCard base={base} meeting={meeting} sync={sync} onChanged={refresh} />
      )}
      {meeting.can_edit && meeting.can_attendance && LIVE_STATES.includes(meeting.status) && (
        <LiveCard base={base} meeting={meeting} onChanged={refresh} />
      )}
      {meeting.can_attendance && meeting.status !== 'cancelled' && (
        <AttendanceCard
          key={`t${meeting.status}${meeting.checkin_open ? 'o' : ''}`}
          base={base}
          meeting={meeting}
          onChanged={refresh}
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
                  await meetingApi.update(base, sync.current(), { status: 'cancelled' })
                  await refresh()
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
                  await meetingApi.update(base, sync.current(), { status: 'held' })
                  await refresh()
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
                  await meetingApi.update(base, sync.current(), { status: 'draft' })
                  await refresh()
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
  sync,
}: {
  base: string
  meeting: Meeting
  kinds: MeetingKind[]
  editable: boolean
  sync: Sync
}) {
  const f = useForm({
    kind: String(meeting.kind),
    title: meeting.title,
    start: local(meeting.starts_at),
    end: local(meeting.ends_at),
    location: meeting.location,
    address: meeting.address,
    chair: meeting.chair ?? '',
    minute_taker: meeting.minute_taker ?? '',
    note: meeting.note ?? '',
  })
  const form = f.values
  const setForm = f.setValues
  // Nur geänderte Felder gehen an den Server; Ungültiges (leerer Titel, Ende vor Beginn)
  // meldet er zurück, die Eingabe bleibt stehen
  const auto = useAutoSave(
    f,
    async (changes) => {
      const data: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(changes)) {
        if (key === 'kind') data.kind = Number(value)
        else if (key === 'start' || key === 'end') {
          const date = new Date(value)
          if (Number.isNaN(date.getTime()))
            throw new ApiError(400, { detail: t('Bitte Beginn und Ende angeben.') })
          data[key === 'start' ? 'starts_at' : 'ends_at'] = date.toISOString()
        } else data[key] = value
      }
      sync.stored(await meetingApi.update(base, sync.current(), data))
    },
    { enabled: editable },
  )
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((v) => ({ ...v, [key]: e.target.value }))
  return (
    <form className="card stack" onSubmit={(e) => e.preventDefault()}>
      <h2>{t('Angaben')}</h2>
      {editable && <SaveStatus auto={auto} />}
      <fieldset disabled={!editable} className="stack">
        <label className="field">
          <span>{t('Art')}</span>
          <select value={form.kind} onChange={set('kind')}>
            {kinds
              .filter((k) => k.active || String(k.id) === form.kind || k.id === meeting.kind)
              .map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Titel')}</span>
          <input value={form.title} maxLength={200} required onChange={set('title')} />
        </label>
        <label className="field">
          <span>{t('Beginn')}</span>
          <input type="datetime-local" required value={form.start} onChange={set('start')} />
        </label>
        <label className="field">
          <span>{t('Ende')}</span>
          <input
            type="datetime-local"
            required
            value={form.end}
            min={form.start || undefined}
            onChange={set('end')}
          />
        </label>
        <PlaceField
          label={t('Ort')}
          value={form.location}
          address={form.address}
          onChange={(value) => setForm((v) => ({ ...v, location: value }))}
          onPick={(place) =>
            setForm((f) => ({ ...f, location: place.name, address: place.address || f.address }))
          }
        />
        <label className="field">
          <span>{t('Anschrift')}</span>
          <input value={form.address} maxLength={300} onChange={set('address')} />
        </label>
        <label className="field">
          <span>{t('Leitung')}</span>
          <input value={form.chair} maxLength={200} onChange={set('chair')} />
        </label>
        <label className="field">
          <span>{t('Protokollführung')}</span>
          <input value={form.minute_taker} maxLength={200} onChange={set('minute_taker')} />
        </label>
        <label className="field">
          <span>{t('Notiz (nur für die Verwaltung)')}</span>
          <textarea value={form.note} maxLength={5000} rows={3} onChange={set('note')} />
        </label>
      </fieldset>
    </form>
  )
}

function agendaRows(agenda: AgendaItem[]): AgendaRow[] {
  return normalize(
    agenda.map((a) => ({
      key: `id-${a.id}`,
      id: a.id,
      title: a.title,
      description: a.description,
      type: a.type,
      level: a.level ? 1 : 0,
    })),
  )
}

function AgendaEditor({
  base,
  meeting,
  editable,
  sync,
}: {
  base: string
  meeting: Meeting
  editable: boolean
  sync: Sync
}) {
  const [items, setItems] = useState(() => agendaRows(meeting.agenda ?? []))
  const [, setErrors] = useState<Record<string, string>>({})
  const [announce, setAnnounce] = useState('')
  const [dragKey, setDragKey] = useState<string | null>(null)
  const newKey = useRef(0)
  const rowEls = useRef(new Map<string, HTMLElement>())
  const handles = useRef(new Map<string, HTMLButtonElement>())
  const focusAfter = useRef<string | null>(null)
  const drag = useRef<{ key: string; target: DropTarget | null } | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const plain = (rows: AgendaRow[]) => rows.map(({ key: _key, ...rest }) => rest)
  // Gespeichert wird die Tagesordnung als Ganzes, sobald jeder Punkt einen Titel hat
  const complete = items.every((item) => item.title.trim() !== '')
  const values = useMemo(() => ({ items }), [items])
  const auto = useAutoSave(
    { values, setErrors },
    async (_changes, current) => {
      const sent = current.items
      const result = await meetingApi.saveAgenda(base, sync.current(), plain(sent))
      sync.stored(result)
      // Neue Punkte bekommen ihre Nummer vom Server, sonst entstünden sie beim nächsten
      // Speichern noch einmal
      const ids = new Map(sent.map((row, i) => [row.key, result.agenda?.[i]?.id]))
      setItems((rows) => {
        let changed = false
        const next = rows.map((row) => {
          const id = ids.get(row.key)
          if (!id || row.id) return row
          changed = true
          return { ...row, id }
        })
        return changed ? next : rows
      })
    },
    { enabled: editable && complete },
  )
  useDraftGuard(editable && !complete, () => setItems(agendaRows(sync.current().agenda ?? [])))
  const numbers = agendaNumbers(items.map((item) => item.level))
  const change = (index: number, patch: Partial<AgendaRow>) =>
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  const nextKey = () => `neu-${(newKey.current += 1)}`

  // Pfeiltasten am Griff: Fokus bleibt auf dem verschobenen Punkt
  useLayoutEffect(() => {
    if (focusAfter.current !== null) {
      handles.current.get(focusAfter.current)?.focus()
      focusAfter.current = null
    }
  })

  const told = (rows: AgendaRow[], key: string) => {
    const at = rows.findIndex((r) => r.key === key)
    const n = agendaNumbers(rows.map((r) => r.level))[at]
    const title = rows[at]?.title || t('Neuer Punkt')
    setAnnounce(t('{x} ist jetzt TOP {n}.', { x: title, n }))
  }

  function startDrag(e: PointerEvent<HTMLElement>, key: string, fromHandle: boolean) {
    if (e.button !== 0) return
    if (!fromHandle) {
      // Auf dem Handy nur am Griff, sonst ließe sich die Seite nicht mehr wischen
      if (e.pointerType === 'touch') return
      const target = e.target as HTMLElement
      if (target.closest('input, select, textarea, a, label, button')) return
    }
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { key, target: null }
    setDragKey(key)
  }

  function moveDrag(e: PointerEvent<HTMLElement>) {
    const d = drag.current
    if (!d) return
    const from = items.findIndex((r) => r.key === d.key)
    if (from < 0) return
    const inBlock = new Set(items.slice(from, blockEnd(items, from)).map((r) => r.key))
    // Mitte eines Punkts = darauf ablegen (Unterpunkt), oberes/unteres Viertel = davor/dahinter
    let target: DropTarget = { kind: 'before', key: null }
    const others = items.filter((r) => !inBlock.has(r.key))
    for (let j = 0; j < others.length; j += 1) {
      const box = rowEls.current.get(others[j].key)?.getBoundingClientRect()
      if (!box || e.clientY > box.bottom) continue
      const rel = (e.clientY - box.top) / box.height
      if (rel < 0.25) target = { kind: 'before', key: others[j].key }
      else if (rel <= 0.75) target = { kind: 'onto', key: others[j].key }
      else target = { kind: 'before', key: others[j + 1]?.key ?? null }
      break
    }
    if (JSON.stringify(target) !== JSON.stringify(d.target)) {
      d.target = target
      setDropTarget(target)
    }
  }

  function endDrag() {
    const d = drag.current
    drag.current = null
    setDragKey(null)
    setDropTarget(null)
    if (d?.target) {
      const next = dropBlock(items, d.key, d.target)
      if (next !== items) {
        setItems(next)
        told(next, d.key)
      }
    }
  }

  function cancelDrag() {
    drag.current = null
    setDragKey(null)
    setDropTarget(null)
  }

  function apply(next: AgendaRow[], key: string) {
    if (next === items) return
    focusAfter.current = key
    setItems(next)
    told(next, key)
  }

  function onHandleKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const key = items[index].key
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault()
      apply(moveRow(items, index, e.key === 'ArrowUp' ? -1 : 1), key)
    } else if (e.key === 'ArrowRight' && !items[index].level) {
      e.preventDefault()
      let p = index - 1
      while (p >= 0 && items[p].level) p -= 1
      if (p >= 0) apply(attach(items, index, items[p].key), key)
    } else if (e.key === 'ArrowLeft' && items[index].level) {
      e.preventDefault()
      apply(attach(items, index, null), key)
    }
  }

  if (!editable) {
    return (
      <section className="card">
        <h2>{t('Tagesordnung')}</h2>
        <ol className="agenda-list">
          {items.map((item, index) => (
            <li key={item.key} className={item.level ? 'agenda-sub' : undefined}>
              <strong>
                {t('TOP {n}', { n: numbers[index] })}: <span>{item.title}</span>
              </strong>
              {item.description && <p className="muted">{item.description}</p>}
            </li>
          ))}
        </ol>
      </section>
    )
  }
  return (
    <form className="card stack" onSubmit={(e) => e.preventDefault()}>
      <h2>{t('Tagesordnung')}</h2>
      {complete ? (
        <SaveStatus auto={auto} />
      ) : (
        <div className="save-status save-status-pending">
          <p role="status" aria-live="polite">
            {t('Noch nicht gespeichert: Jeder Punkt braucht einen Titel.')}
          </p>
        </div>
      )}
      <p className="muted small">
        {t(
          'Punkte am Griff oder an einer freien Stelle ziehen: zwischen zwei Punkten ablegen, um die Reihenfolge zu ändern, oder auf einem Punkt ablegen, um ihn zu dessen Unterpunkt zu machen. Unterpunkte ziehen mit ihrem Punkt mit. Am Griff gehen auch die Pfeiltasten (→ Unterpunkt, ← eigener Punkt).',
        )}
      </p>
      <ol className="agenda-edit">
        {items.map((item, index) => {
          const n = numbers[index]
          const parents = items.filter((r, j) => !r.level && j !== index)
          const parent = item.level ? items[parentIndex(items, index)] : undefined
          return (
            <li
              key={item.key}
              ref={(el) => {
                if (el) rowEls.current.set(item.key, el)
                else rowEls.current.delete(item.key)
              }}
              className={[
                'agenda-row',
                item.level && 'agenda-sub',
                dragKey === item.key && 'sortable-dragging',
                dragKey &&
                  dropTarget?.key === item.key &&
                  (dropTarget.kind === 'onto' ? 'agenda-drop-onto' : 'agenda-drop-before'),
                dragKey &&
                  dropTarget?.kind === 'before' &&
                  dropTarget.key === null &&
                  index === items.length - 1 &&
                  'agenda-drop-after',
              ]
                .filter(Boolean)
                .join(' ')}
              onPointerDown={(e) => startDrag(e, item.key, false)}
              onPointerMove={moveDrag}
              onPointerUp={endDrag}
              onPointerCancel={cancelDrag}
            >
              <div className="agenda-fields">
                <label className="field">
                  <span>{t('TOP {n}', { n })}</span>
                  <input
                    value={item.title}
                    maxLength={300}
                    required
                    onChange={(e) => change(index, { title: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span>{t('Art des Punkts')}</span>
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
                {index > 0 && (
                  <label className="field">
                    <span>{t('Gehört zu')}</span>
                    <select
                      value={parent?.key ?? ''}
                      onChange={(e) =>
                        apply(attach(items, index, e.target.value || null), item.key)
                      }
                    >
                      <option value="">{t('Eigener Punkt (oberste Ebene)')}</option>
                      {parents.map((p) => (
                        <option key={p.key} value={p.key}>
                          {t('Unterpunkt von TOP {n}', { n: numbers[items.indexOf(p)] })}
                          {p.title ? `: ${p.title}` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="field agenda-wide">
                  <span>{t('Erläuterung')}</span>
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
                  className="drag-handle"
                  ref={(el) => {
                    if (el) handles.current.set(item.key, el)
                    else handles.current.delete(item.key)
                  }}
                  aria-label={t('TOP {n} verschieben', { n })}
                  aria-roledescription={t('Griff zum Verschieben')}
                  title={t(
                    'Ziehen zum Verschieben (Pfeiltasten: ↑ ↓ verschieben, → Unterpunkt, ← eigener Punkt)',
                  )}
                  onPointerDown={(e) => {
                    e.stopPropagation()
                    startDrag(e, item.key, true)
                  }}
                  onKeyDown={(e) => onHandleKey(e, index)}
                >
                  <GripIcon />
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={!canMove(items, index, -1)}
                  aria-label={t('TOP {n} nach oben', { n })}
                  onClick={() => apply(moveRow(items, index, -1), item.key)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={!canMove(items, index, 1)}
                  aria-label={t('TOP {n} nach unten', { n })}
                  onClick={() => apply(moveRow(items, index, 1), item.key)}
                >
                  ↓
                </button>
                {!item.level && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setItems(addSub(items, index, nextKey()))}
                  >
                    {t('Unterpunkt hinzufügen')}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={async () => {
                    // Gespeicherte Punkte verschwinden sofort: vorher fragen
                    if (
                      item.id &&
                      !(await confirmDialog({
                        title: t('Tagesordnungspunkt entfernen?'),
                        message: t(
                          '„{title}“ wird mit seiner Erläuterung gelöscht. Unterpunkte bleiben als eigene Punkte stehen.',
                          { title: item.title },
                        ),
                        confirmLabel: t('Entfernen'),
                      }))
                    )
                      return
                    setItems((rows) => {
                      const at = rows.findIndex((r) => r.key === item.key)
                      return at < 0 ? rows : removeRow(rows, at)
                    })
                  }}
                >
                  {t('Entfernen')}
                </button>
              </div>
            </li>
          )
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            setItems([
              ...items,
              { key: nextKey(), title: '', description: '', type: 'other', level: 0 },
            ])
          }
        >
          {t('Punkt hinzufügen')}
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
      <div className="aid-row">
        <Why k="meeting_invite" />
        <Why k="meeting_quorum" />
        <Why k="meeting_proxies" />
        <Why k="meeting_motions" />
      </div>
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
    online_voting: kind?.online_voting ?? false,
    remote_allowed: kind?.remote_allowed ?? false,
    active: kind?.active ?? true,
  }
  const f = useForm(initial)
  const form = f.values
  const setForm = f.setValues
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const toInput = (values: Partial<typeof initial>) => {
    const data: Record<string, unknown> = { ...values }
    if ('invite_days' in values) data.invite_days = Number(values.invite_days)
    if ('quorum_percent' in values)
      data.quorum_percent = values.quorum_percent ? Number(values.quorum_percent) : null
    if ('motion_days' in values)
      data.motion_days = values.motion_days === '' ? null : Number(values.motion_days)
    return data
  }
  // Bestehende Arten speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    f,
    async (changes) => {
      if (changes.invite_days === '')
        throw new ApiError(400, { invite_days: t('Bitte eine Frist angeben.') })
      await meetingApi.updateKind(base, kind!.id, toInput(changes))
    },
    { enabled: !!kind },
  )
  useDraftGuard(!kind && JSON.stringify(form) !== JSON.stringify(initial))
  return (
    <form
      className="stack kind-form"
      onSubmit={async (e) => {
        e.preventDefault()
        if (kind) return
        setBusy(true)
        setError('')
        try {
          await meetingApi.createKind(base, toInput(form))
          onDone(true)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <h3>{kind ? t('Art bearbeiten') : t('Neue Art')}</h3>
      {kind && <SaveStatus auto={auto} />}
      <label className="field">
        <span>{t('Name')}</span>
        <input
          value={form.name}
          maxLength={100}
          required
          onChange={(e) => setForm((v) => ({ ...v, name: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Grundtyp')}</span>
        <select
          value={form.base}
          onChange={(e) => setForm((v) => ({ ...v, base: e.target.value as MeetingBase }))}
        >
          {BASES.map((b) => (
            <option key={b} value={b}>
              {baseLabel(b)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('Einladungsfrist in Tagen')}</span>
        <input
          type="number"
          min={0}
          max={365}
          required
          value={form.invite_days}
          onChange={(e) => setForm((v) => ({ ...v, invite_days: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Einladung')}</span>
        <select
          value={form.invite_form}
          onChange={(e) =>
            setForm((v) => ({ ...v, invite_form: e.target.value as MeetingKind['invite_form'] }))
          }
        >
          <option value="mail">{t('E-Mail, sonst Brief')}</option>
          <option value="letter">{t('Brief an alle')}</option>
        </select>
      </label>
      <label className="field">
        <span>{t('Beschlussfähig ab (Prozent der Stimmberechtigten, leer: immer)')}</span>
        <input
          type="number"
          min={1}
          max={100}
          value={form.quorum_percent}
          onChange={(e) => setForm((v) => ({ ...v, quorum_percent: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Protokoll sehen')}</span>
        <select
          value={form.minutes_for}
          onChange={(e) =>
            setForm((v) => ({ ...v, minutes_for: e.target.value as MeetingKind['minutes_for'] }))
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
          onChange={(e) => setForm((v) => ({ ...v, proxies_allowed: e.target.checked }))}
        />
        {t('Vertretung mit Vollmacht erlaubt')}
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.online_voting}
          onChange={(e) => setForm((v) => ({ ...v, online_voting: e.target.checked }))}
        />
        {t('Online-Abstimmung am Handy erlaubt')}
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.remote_allowed}
          onChange={(e) => setForm((v) => ({ ...v, remote_allowed: e.target.checked }))}
        />
        {t('Teilnahme aus der Ferne erlaubt (hybride Versammlung)')}
      </label>
      {form.remote_allowed && (
        <p className="muted small">
          {t(
            'Teilnahme und Abstimmung aus der Ferne braucht eine Grundlage in der Satzung oder einen Beschluss der Mitgliederversammlung (§ 32 Abs. 2 BGB). Bitte vorher prüfen.',
          )}
        </p>
      )}
      <label className="field">
        <span>{t('Anträge von Mitgliedern bis Tage vorher (leer: keine Anträge)')}</span>
        <input
          type="number"
          min={0}
          max={90}
          value={form.motion_days}
          onChange={(e) => setForm((v) => ({ ...v, motion_days: e.target.value }))}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.active}
          onChange={(e) => setForm((v) => ({ ...v, active: e.target.checked }))}
        />
        {t('Für neue Versammlungen wählbar')}
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        {kind ? (
          <button
            type="button"
            className="button"
            onClick={async () => {
              // Schließt erst, wenn alles gespeichert ist
              if (await auto.flush()) onDone(true)
            }}
          >
            {t('Schließen')}
          </button>
        ) : (
          <>
            <button className="button button-primary" disabled={busy}>
              {t('Anlegen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
              {t('Abbrechen')}
            </button>
          </>
        )}
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
      {meeting.status === 'draft' && !meeting.invited_at && (
        <Checklist
          title={t('Vor der Einladung')}
          items={meetingInviteChecks({
            inviteBy: meeting.invite_by,
            agenda: meeting.agenda ?? [],
          })}
        />
      )}
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
  if (status === 'left') return t('Gegangen')
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
  // Während die Anmeldung per App offen ist, kommen Einträge von selbst hinzu
  useEffect(() => {
    if (!meeting.checkin_open) return
    const timer = window.setInterval(() => {
      if (document.hidden) return
      meetingApi
        .attendance(base, meeting.id)
        .then(setList)
        .catch(() => undefined)
    }, 10000)
    return () => window.clearInterval(timer)
  }, [base, meeting.id, meeting.checkin_open])
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!data) return <Loading />
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
        {(data.online ?? 0) > 0 && ` ${t('Davon aus der Ferne: {n}.', { n: data.online ?? 0 })}`}
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
                  {row.status === 'present' && row.mode === 'app' && (
                    <span className="badge">{t('per App')}</span>
                  )}
                  {row.status === 'present' && row.mode === 'online' && (
                    <span className="badge">{t('aus der Ferne')}</span>
                  )}
                  {row.status === 'left' && <span className="badge">{t('gegangen')}</span>}
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

function minutesItems(agenda: AgendaItem[]): MinutesItem[] {
  return agenda.map((a) => ({
    id: a.id!,
    minutes: a.minutes ?? '',
    resolutions: (a.resolutions ?? []).map((r) => ({ ...r })),
  }))
}

/** So vollständig, dass der Server den Eintrag annimmt. */
function resolutionComplete(r: Resolution): boolean {
  if (r.kind === 'election') return !!r.office.trim() && (!!r.elected_name.trim() || !!r.elected)
  return !!r.text.trim()
}

function MinutesEditor({
  base,
  meeting,
  editable,
  sync,
}: {
  base: string
  meeting: Meeting
  editable: boolean
  sync: Sync
}) {
  const agenda = meeting.agenda ?? []
  const [items, setItems] = useState(() => minutesItems(agenda))
  const [, setErrors] = useState<Record<string, string>>({})
  // Gespeichert wird das Protokoll als Ganzes, sobald kein Beschluss und keine Wahl mehr
  // halb ausgefüllt ist
  const complete = items.every((item) => item.resolutions.every(resolutionComplete))
  const values = useMemo(() => ({ items }), [items])
  const auto = useAutoSave(
    { values, setErrors },
    async (_changes, current) => {
      const sent = current.items
      const result = await meetingApi.saveMinutes(base, sync.current(), sent)
      sync.stored(result)
      // Neue Beschlüsse und Wahlen bekommen ihre Nummer vom Server, sonst entstünden sie
      // beim nächsten Speichern noch einmal
      const stored = new Map((result.agenda ?? []).map((a) => [a.id, a.resolutions ?? []]))
      const counts = new Map(sent.map((item) => [item.id, item.resolutions.length]))
      setItems((rows) => {
        let changed = false
        const next = rows.map((row) => {
          const server = stored.get(row.id)
          if (!server || row.resolutions.length !== counts.get(row.id)) return row
          let touched = false
          const resolutions = row.resolutions.map((r, j) => {
            const id = server[j]?.id
            if (r.id || !id) return r
            touched = true
            return { ...r, id }
          })
          if (!touched) return row
          changed = true
          return { ...row, resolutions }
        })
        return changed ? next : rows
      })
    },
    { enabled: editable && complete },
  )
  useDraftGuard(editable && !complete, () => setItems(minutesItems(sync.current().agenda ?? [])))
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
          {agenda.map((a, index) => (
            <li key={a.id!} className={a.level ? 'agenda-sub' : undefined}>
              <strong>
                {t('TOP {n}', { n: a.number || index + 1 })}: <span>{a.title}</span>
              </strong>
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
    <form className="card stack" onSubmit={(e) => e.preventDefault()}>
      <h2>{t('Protokoll der Versammlung')}</h2>
      {complete ? (
        <SaveStatus auto={auto} />
      ) : (
        <div className="save-status save-status-pending">
          <p role="status" aria-live="polite">
            {t(
              'Noch nicht gespeichert: Ein Beschluss braucht einen Text, eine Wahl das Amt und die gewählte Person.',
            )}
          </p>
        </div>
      )}
      <p className="muted">
        {t(
          'Halte je Tagesordnungspunkt fest, was besprochen wurde, und trage Beschlüsse und Wahlen mit dem Ergebnis ein.',
        )}
      </p>
      <p className="muted small">
        {t('Es gilt meist die')} <Term k="simple_majority">{t('einfache Mehrheit')}</Term>
        {t('; für eine')} <Term k="statute_amendment">{t('Satzungsänderung')}</Term>{' '}
        {t('braucht es drei Viertel, wenn die Satzung nichts anderes sagt.')}
      </p>
      <HowTo k="calc_vote_result" />
      <ol className="agenda-edit">
        {items.map((item, index) => (
          <li
            key={item.id}
            className={agenda[index].level ? 'agenda-row agenda-sub' : 'agenda-row'}
          >
            <h3>
              {t('TOP {n}', { n: agenda[index].number || index + 1 })}:{' '}
              <span>{agenda[index].title}</span>
            </h3>
            <label className="field">
              <span>{t('Protokoll zu TOP {n}', { n: agenda[index].number || index + 1 })}</span>
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
                    <label className="field">
                      <span>{t('Amt')}</span>
                      <input
                        value={r.office}
                        maxLength={200}
                        required
                        onChange={(e) => changeResolution(index, j, { office: e.target.value })}
                      />
                    </label>
                    <label className="field">
                      <span>{t('Gewählt')}</span>
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
                  <label className="field">
                    <span>{t('Beschlusstext')}</span>
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
                    <label className="field">
                      <span>{t('Ja')}</span>
                      <input
                        type="number"
                        min={0}
                        value={r.votes_yes ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_yes: count(e.target.value) })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>{t('Nein')}</span>
                      <input
                        type="number"
                        min={0}
                        value={r.votes_no ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_no: count(e.target.value) })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>{t('Enthaltung')}</span>
                      <input
                        type="number"
                        min={0}
                        value={r.votes_abstain ?? ''}
                        onChange={(e) =>
                          changeResolution(index, j, { votes_abstain: count(e.target.value) })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>{t('Ergebnis')}</span>
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
    </form>
  )
}

function ReleaseCard({
  base,
  meeting,
  sync,
  onChanged,
}: {
  base: string
  meeting: Meeting
  sync: Sync
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
      <Why k="meeting_minutes" />
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
                    // Bestätigt wird der gespeicherte Stand: erst alles speichern
                    if (!(await flushAllForms())) {
                      setError(t('Das Protokoll ist noch nicht vollständig gespeichert.'))
                      return
                    }
                    await meetingApi.confirmMinutes(base, sync.current(), r.role)
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
            run(async () => {
              await flushAllForms()
              saveBlob(
                await meetingApi.minutesPdf(base, meeting),
                done ? 'protokoll.pdf' : 'protokoll-entwurf.pdf',
              )
            })
          }
        >
          {done ? t('Protokoll als PDF') : t('Vorschau als PDF')}
        </button>
      </div>
    </section>
  )
}
