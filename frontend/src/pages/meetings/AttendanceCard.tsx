import { useEffect, useState } from 'react'
import { meetingApi } from '../../api/meetings.ts'
import type {
  AttendanceList,
  AttendanceRow,
  AttendanceStatus,
  Meeting,
} from '../../api/meetings.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import { Loading } from '../../components/ui.tsx'
import './meetings.css'

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

export function AttendanceCard({
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
