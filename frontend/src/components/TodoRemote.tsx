import { useState } from 'react'
import { api } from '../api/client.ts'
import type { Todo } from '../api/todos.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError, SelectField } from './ui.tsx'
import { confirmLeave } from './leaveGuard.ts'
import { t } from '../i18n/index.ts'

interface Grant {
  coupling: number
  mode: 'copy' | 'common'
  active: boolean
  can_complete: boolean
  following: boolean
  progress: {
    sequence_no: number
    due_date: string | null
    status: string
    ended: boolean
    deleted: boolean
  }[]
}

export function TodoRemote({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const endpoint = `${base}${todo.id}/remote/`
  const { data, error, reload } = useLoad(
    () =>
      api.get<{
        version: number
        couplings: { id: number; name: string; enabled: boolean }[]
        shares: Grant[]
      }>(endpoint),
    [endpoint, todo.version],
  )
  return (
    <details className="card">
      <summary>{t('Mit anderer Installation teilen')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      <p>
        {t(
          'Die Kopplung muss Aufgaben freigeben und die andere Seite muss den Empfang bestätigen. Geteilt werden nur diese Aufgabe und ausdrücklich freigegebene Folgeausgaben. Lokale Notizen und Ergänzungen bleiben vor Ort.',
        )}
      </p>
      {data && !data.couplings.length && <p>{t('Keine aktive Kopplung vorhanden.')}</p>}
      <div className="stack">
        {data?.couplings.map((coupling) => (
          <RemoteGrant
            key={`${coupling.id}-${data.version}`}
            coupling={coupling}
            version={data.version}
            recurring={!!todo.series}
            endpoint={endpoint}
            initial={data.shares.find((s) => s.coupling === coupling.id)}
            onSaved={() => {
              void reload()
              onSaved()
            }}
          />
        ))}
      </div>
    </details>
  )
}

function RemoteGrant({
  coupling,
  version,
  recurring,
  endpoint,
  initial,
  onSaved,
}: {
  coupling: { id: number; name: string; enabled: boolean }
  version: number
  recurring: boolean
  endpoint: string
  initial?: Grant
  onSaved: () => void
}) {
  const [active, setActive] = useState(initial?.active ?? false)
  const [mode, setMode] = useState<Grant['mode']>(initial?.mode ?? 'copy')
  const [complete, setComplete] = useState(initial?.can_complete ?? true)
  const [following, setFollowing] = useState(initial?.following ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <section className="subcard stack">
      <h3>{coupling.name}</h3>
      {!coupling.enabled && <p>{t('Bitte Aufgaben zuerst in der Kopplung freigeben.')}</p>}
      <Checkbox
        label={t('Aufgabe für diese Installation freigeben')}
        checked={active}
        onChange={setActive}
        disabled={busy || (!coupling.enabled && !initial?.active)}
      />
      <SelectField
        label={t('Erledigung zwischen Installationen')}
        value={mode}
        disabled={busy || !!initial}
        onChange={(event) => setMode(event.target.value as Grant['mode'])}
      >
        <option value="copy">{t('Eigene Kopie mit eigenem Erledigungsstand')}</option>
        <option value="common">{t('Eine gemeinsam erledigte Aufgabe')}</option>
      </SelectField>
      <p>
        {mode === 'copy'
          ? t(
              'Die Zieleinheit übernimmt eine eigene Aufgabe. Die Quelle sieht nur ihren Fortschritt. Ein Widerruf stoppt die weitere Versorgung; bereits übernommene Inhalte bleiben vor Ort.',
            )
          : t(
              'Alle Beteiligten arbeiten am selben Erledigungsstand der Quelle. Zum Lesen und Erledigen muss die Quelle erreichbar sein. Ein Widerruf entzieht den Zugriff.',
            )}
      </p>
      <Checkbox
        label={t('Erledigen auf der anderen Installation erlauben')}
        checked={complete}
        onChange={setComplete}
        disabled={busy}
      />
      {recurring && (
        <Checkbox
          label={t('Auch folgende Ausgaben freigeben')}
          checked={following}
          onChange={setFollowing}
          disabled={busy}
        />
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          className="button"
          disabled={busy}
          onClick={async () => {
            if (!(await confirmLeave())) return
            setBusy(true)
            setError(null)
            try {
              await api.put(endpoint, {
                version,
                coupling: coupling.id,
                active,
                mode,
                can_complete: complete,
                following,
              })
              onSaved()
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          {t('Freigabe speichern')}
        </button>
      </div>
      {!!initial?.progress.length && (
        <table>
          <caption>{t('Fortschritt der Zieleinheit')}</caption>
          <thead>
            <tr>
              <th>{t('Ausgabe')}</th>
              <th>{t('Frist')}</th>
              <th>{t('Status')}</th>
            </tr>
          </thead>
          <tbody>
            {initial.progress.map((row) => (
              <tr key={row.sequence_no}>
                <td>{row.sequence_no}</td>
                <td>{row.due_date ?? '–'}</td>
                <td>
                  {row.deleted
                    ? t('Papierkorb')
                    : row.status === 'done'
                      ? t('Erledigt')
                      : t('Offen')}
                  {row.ended ? ` · ${t('Beendet')}` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export function TodoRemoteInbox({ base, onSaved }: { base: string; onSaved: () => void }) {
  const endpoint = `${base}remote/`
  const { data, error, reload } = useLoad(
    () =>
      api.get<{
        items: { id: number; from: string; title: string; description: string; mode: string }[]
      }>(endpoint),
    [endpoint],
  )
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  return (
    <details className="card">
      <summary>{t('Aufgaben aus anderen Installationen')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {data && !data.items.length && <p>{t('Keine neuen Aufgaben zur Übernahme.')}</p>}
      <div className="stack">
        {data?.items.map((item) => (
          <section className="subcard stack" key={item.id}>
            <h3>{item.title}</h3>
            <p>
              {item.from} ·{' '}
              {item.mode === 'common'
                ? t('Eine gemeinsam erledigte Aufgabe')
                : t('Eigene Kopie mit eigenem Erledigungsstand')}
            </p>
            <p className="todo-description">{item.description}</p>
            <button
              className="button"
              disabled={busy}
              onClick={async () => {
                if (!(await confirmLeave())) return
                setBusy(true)
                setActionError(null)
                try {
                  await api.post(`${endpoint}${item.id}/adopt/`, {})
                  await reload()
                  onSaved()
                } catch (err) {
                  setActionError(errorMessage(err))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Übernehmen')}
            </button>
          </section>
        ))}
      </div>
    </details>
  )
}
