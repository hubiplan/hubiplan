import { useMemo, useState } from 'react'
import { meetingApi } from '../../api/meetings.ts'
import type { AgendaItem, Meeting, MinutesItem, Resolution } from '../../api/meetings.ts'
import { useAutoSave } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { HowTo, Term } from '../../learning/Aids.tsx'
import { SaveStatus } from '../../components/ui.tsx'
import './meetings.css'
import { type Sync } from './meetingsHelpers.ts'

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

export function MinutesEditor({
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
