// Beschlussbuch (konzepte/versammlungen.md, Schritt V5): alle freigegebenen Beschlüsse und
// Wahlen mit Suche, Filtern, Stand der Umsetzung, Aufgabe und Excel-Liste.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { orgApi } from '../../api/orgs.ts'
import { meetingApi } from '../../api/meetings.ts'
import type { BookRow, MeetingKind, ResolutionStatus } from '../../api/meetings.ts'
import { AssignRoleDialog } from '../../components/AssignRoleDialog.tsx'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { locale, t } from '../../i18n/index.ts'

function statusLabel(status: ResolutionStatus) {
  if (status === 'done') return t('umgesetzt')
  if (status === 'repealed') return t('aufgehoben')
  return t('offen')
}

function votes(row: BookRow) {
  if (row.unanimous) return t('einstimmig')
  const parts = [row.votes_yes, row.votes_no, row.votes_abstain]
  if (parts.every((v) => v === null)) return ''
  return t('Ja {yes} · Nein {no} · Enthaltung {abstain}', {
    yes: row.votes_yes ?? 0,
    no: row.votes_no ?? 0,
    abstain: row.votes_abstain ?? 0,
  })
}

function dateText(value: string) {
  return new Date(value + 'T12:00:00Z').toLocaleDateString(locale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/** Rolle passend zum Amt aus der Wahl (gleicher Name, Groß-/Kleinschreibung egal) */
function roleForOffice(roles: { id: number; name: string }[], office: string) {
  const wanted = office.trim().toLocaleLowerCase()
  return wanted ? roles.find((r) => r.name.trim().toLocaleLowerCase() === wanted)?.id : undefined
}

export function ResolutionBook({
  base,
  canEdit,
  kinds,
  assignOrg = null,
}: {
  base: string
  canEdit: boolean
  kinds: MeetingKind[]
  /** Verein, in dem Gewählte ins Amt übernommen werden dürfen (Rollenverwaltung) */
  assignOrg?: number | null
}) {
  const [term, setTerm] = useState('')
  const [year, setYear] = useState('')
  const [kind, setKind] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const params = new URLSearchParams()
  if (term.trim()) params.set('suche', term.trim())
  if (year) params.set('jahr', year)
  if (kind) params.set('art', kind)
  if (type) params.set('typ', type)
  if (status) params.set('stand', status)
  const query = params.toString() ? `?${params}` : ''
  const book = useLoad(() => meetingApi.book(base, query), [base, query])
  const [error, setError] = useState('')
  const act = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
      await book.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const rows = book.data?.rows ?? []
  // Wahlen ins Amt übernehmen: Rollen und heutige Amtszeiten nur mit Rollenverwaltung
  const roles = useLoad(
    () => (assignOrg ? orgApi.roles(assignOrg) : Promise.resolve([])),
    [assignOrg],
  )
  const assignments = useLoad(
    () => (assignOrg ? orgApi.assignments(assignOrg) : Promise.resolve([])),
    [assignOrg],
  )
  const [electing, setElecting] = useState<BookRow | null>(null)
  const canTakeOver = (r: BookRow) =>
    !!assignOrg &&
    canEdit &&
    r.kind === 'election' &&
    r.result === 'accepted' &&
    r.elected !== null &&
    r.status === 'open' &&
    (roles.data?.length ?? 0) > 0
  return (
    <section className="card stack" aria-labelledby="resolution-book">
      <h2 id="resolution-book">{t('Beschlussbuch')}</h2>
      <p className="muted">
        {t('Hier stehen alle Beschlüsse und Wahlen aus freigegebenen Protokollen.')}
      </p>
      <div className="book-filters">
        <label className="field">
          <span>{t('Suche')}</span>
          <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('Jahr')}</span>
          <select value={year} onChange={(e) => setYear(e.target.value)}>
            <option value="">{t('alle')}</option>
            {(book.data?.years ?? []).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Art der Versammlung')}</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t('alle')}</option>
            {kinds.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Beschluss oder Wahl')}</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">{t('alle')}</option>
            <option value="resolution">{t('Beschlüsse')}</option>
            <option value="election">{t('Wahlen')}</option>
          </select>
        </label>
        <label className="field">
          <span>{t('Stand der Umsetzung')}</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t('alle')}</option>
            <option value="open">{t('offen')}</option>
            <option value="done">{t('umgesetzt')}</option>
            <option value="repealed">{t('aufgehoben')}</option>
          </select>
        </label>
      </div>
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          disabled={rows.length === 0}
          onClick={() =>
            act(async () =>
              saveBlob(await meetingApi.bookExport(base, query), 'beschlussbuch.xlsx'),
            )
          }
        >
          {t('Liste als Excel')}
        </button>
      </div>
      {(book.error || error) && <p role="alert">{book.error || error}</p>}
      {book.data && rows.length === 0 ? (
        <p className="muted">{t('Keine Beschlüsse gefunden.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Nummer')}</th>
              <th>{t('Beschluss')}</th>
              <th>{t('Ergebnis')}</th>
              <th>{t('Stand')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.number}</strong>
                  <div className="muted small">{dateText(r.date)}</div>
                </td>
                <td>
                  {r.kind === 'election' ? (
                    <>
                      <strong>{t('Wahl: {office}', { office: r.office })}</strong>
                      {r.elected_name && ` · ${r.elected_name}`}
                      {r.text && <div>{r.text}</div>}
                    </>
                  ) : (
                    <div style={{ whiteSpace: 'pre-wrap' }}>{r.text}</div>
                  )}
                  <div className="muted small">
                    {r.meeting_title} ·{' '}
                    {r.agenda_number
                      ? t('TOP {n}: {title}', { n: r.agenda_number, title: r.agenda_title })
                      : r.agenda_title}
                  </div>
                </td>
                <td>
                  {r.result === 'accepted' ? t('angenommen') : t('abgelehnt')}
                  <div className="muted small">{votes(r)}</div>
                </td>
                <td>
                  {canEdit ? (
                    <select
                      aria-label={t('Stand von Beschluss {number}', { number: r.number })}
                      value={r.status}
                      onChange={(e) =>
                        act(() =>
                          meetingApi.setResolutionStatus(
                            base,
                            r.id,
                            e.target.value as ResolutionStatus,
                          ),
                        )
                      }
                    >
                      <option value="open">{t('offen')}</option>
                      <option value="done">{t('umgesetzt')}</option>
                      <option value="repealed">{t('aufgehoben')}</option>
                    </select>
                  ) : (
                    statusLabel(r.status)
                  )}
                  {canTakeOver(r) && (
                    <div>
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('Wahl {number} ins Amt übernehmen', { number: r.number })}
                        onClick={() => setElecting(r)}
                      >
                        {t('Ins Amt übernehmen')}
                      </button>
                    </div>
                  )}
                  {r.todo ? (
                    <div className="muted small">
                      {t('Aufgabe: {title}', { title: r.todo.title })}
                    </div>
                  ) : r.has_todo ? (
                    <div className="muted small">{t('Aufgabe angelegt')}</div>
                  ) : (
                    canEdit &&
                    book.data?.can_todo &&
                    r.status === 'open' && (
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('Beschluss {number} als Aufgabe anlegen', {
                          number: r.number,
                        })}
                        onClick={() => act(() => meetingApi.resolutionTodo(base, r.id, {}))}
                      >
                        {t('Als Aufgabe anlegen')}
                      </button>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {electing && assignOrg && electing.elected !== null && roles.data && assignments.data && (
        <AssignRoleDialog
          orgId={assignOrg}
          roles={roles.data}
          assignments={assignments.data}
          suggestedRole={roleForOffice(roles.data, electing.office)}
          from={electing.date}
          member={{ id: electing.elected, first_name: electing.elected_name, last_name: '' }}
          onClose={() => setElecting(null)}
          onDone={async () => {
            // Gewählte Person ist im Amt: Beschluss gilt als umgesetzt
            await meetingApi.setResolutionStatus(base, electing.id, 'done')
            await Promise.all([book.reload(), assignments.reload()])
          }}
        />
      )}
    </section>
  )
}
