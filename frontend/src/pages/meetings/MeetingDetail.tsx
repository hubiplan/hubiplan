import { NextcloudSave } from '../../components/NextcloudFiles.tsx'
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { berlin } from '../../components/calendar/time.ts'
import { meetingApi } from '../../api/meetings.ts'
import type { Confirmation, Meeting, MeetingKind, MeetingStatus } from '../../api/meetings.ts'
import { ApiError, saveBlob } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { flushAllForms } from '../../components/leaveGuard.ts'
import { locale, t, tc } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { meetingInviteChecks } from '../../learning/checks.ts'
import { MotionsCard } from './MotionsCard.tsx'
import { LiveCard } from './LiveCard.tsx'
import { LIVE_STATES } from './live.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading, SaveStatus } from '../../components/ui.tsx'
import './meetings.css'
import { PlaceField } from '../../components/PlaceField.tsx'
import { ZONE, local, statusLabel, when, type Sync } from './meetingsHelpers.ts'
import { AgendaEditor } from './AgendaEditor.tsx'
import { AttendanceCard } from './AttendanceCard.tsx'
import { MinutesEditor } from './MinutesEditor.tsx'

function day(value: string) {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString(locale(), { timeZone: 'UTC' })
}

export function MeetingDetail({
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
                    final: false,
                    title: t('Versammlung absagen?'),
                    message: t('Der Termin bleibt im Kalender und wird als abgesagt gezeigt.'),
                    confirmLabel: tc('meeting', 'Absagen'),
                  })
                  if (!yes) return
                  await meetingApi.update(base, sync.current(), { status: 'cancelled' })
                  await refresh()
                })
              }
            >
              {tc('meeting', 'Absagen')}
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
                    danger: false,
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
                    final: true,
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

const MINUTES_STATES: MeetingStatus[] = ['held', 'minutes', 'done']

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
          {meeting.four_eyes
            ? ' ' + t('Die beiden Bestätigungen kommen von zwei verschiedenen Personen.')
            : ''}
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
                      danger: false,
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
        {done && (
          <NextcloudSave
            source={() => meetingApi.minutesPdf(base, meeting)}
            filename={`protokoll-${meeting.starts_at.slice(0, 10)}.pdf`}
            category="records"
            target="board"
          />
        )}
      </div>
    </section>
  )
}
