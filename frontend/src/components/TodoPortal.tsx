import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client.ts'
import type { Todo } from '../api/todos.ts'
import { useLoad, errorMessage } from './forms.ts'
import { Checkbox, LoadError, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { useDraftGuard } from './leaveGuard.ts'

interface Publication {
  enabled: boolean
  active: boolean
  mode: 'assigned' | 'offer'
  following: boolean
  recipients: { access_id: number; can_complete: boolean }[]
  choices: { id: number; name: string }[]
  claimed_by: number | null
  version: number
}

export function TodoPortal({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const endpoint = `${base}${todo.id}/portal/`
  const { data, error, reload } = useLoad(
    () => api.get<Publication>(endpoint),
    [endpoint, todo.version],
  )
  return (
    <details className="card">
      <summary>{t('Im Mitgliederbereich teilen')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      {data && (
        <PublicationEditor
          data={data}
          endpoint={endpoint}
          recurring={!!todo.series}
          onSaved={onSaved}
        />
      )}
    </details>
  )
}

function PublicationEditor({
  data,
  endpoint,
  recurring,
  onSaved,
}: {
  data: Publication
  endpoint: string
  recurring: boolean
  onSaved: () => void
}) {
  const [active, setActive] = useState(data.active)
  const [mode, setMode] = useState(data.mode)
  const [following, setFollowing] = useState(data.following)
  const [recipients, setRecipients] = useState(data.recipients)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const values = { active, mode, following, recipients }
  const [baseline, setBaseline] = useState(
    JSON.stringify({
      active: data.active,
      mode: data.mode,
      following: data.following,
      recipients: data.recipients,
    }),
  )
  const version = useRef(data.version)
  useEffect(() => {
    const incoming = JSON.stringify({
      active: data.active,
      mode: data.mode,
      following: data.following,
      recipients: data.recipients,
    })
    if (incoming === baseline) version.current = data.version
    else if (JSON.stringify({ active, mode, following, recipients }) === baseline) {
      setBaseline(incoming)
      version.current = data.version
      setActive(data.active)
      setMode(data.mode)
      setFollowing(data.following)
      setRecipients(data.recipients)
    }
  }, [data, active, mode, following, recipients, baseline])
  useDraftGuard(JSON.stringify(values) !== baseline, () => {
    const saved = JSON.parse(baseline) as typeof values
    setActive(saved.active)
    setMode(saved.mode)
    setFollowing(saved.following)
    setRecipients(saved.recipients)
  })
  return (
    <div className="stack">
      <p>
        {t(
          'Nur ausdrücklich freigegebene Aufgaben erscheinen für Mitglieder. Die Verantwortung bleibt beim bisherigen Konto.',
        )}
      </p>
      {!data.enabled && (
        <p>{t('Der Mitgliederbereich ist für diese Einheit nicht freigeschaltet.')}</p>
      )}
      <Checkbox
        label={t('Im Mitgliederbereich freigeben')}
        checked={active}
        onChange={setActive}
        disabled={busy || !data.enabled}
      />
      <SelectField
        label={t('Mitgliederfreigabe')}
        value={mode}
        disabled={busy}
        onChange={(event) => setMode(event.target.value as Publication['mode'])}
      >
        <option value="assigned">{t('Ausgewählte Mitglieder')}</option>
        <option value="offer">{t('Offenes Angebot zum Übernehmen')}</option>
      </SelectField>
      {mode === 'offer' ? (
        <p>
          {t(
            'Aktuelle Mitglieder können die Aufgabe sehen. Genau eine Person kann sie übernehmen und danach erledigen.',
          )}
        </p>
      ) : (
        data.choices.map((choice) => {
          const selected = recipients.find((row) => row.access_id === choice.id)
          return (
            <div className="subcard stack-sm" key={choice.id}>
              <Checkbox
                label={choice.name}
                checked={!!selected}
                onChange={(checked) =>
                  setRecipients(
                    checked
                      ? [...recipients, { access_id: choice.id, can_complete: true }]
                      : recipients.filter((row) => row.access_id !== choice.id),
                  )
                }
                disabled={busy}
              />
              {selected && (
                <Checkbox
                  label={t('Darf erledigen und wieder öffnen')}
                  checked={selected.can_complete}
                  onChange={(checked) =>
                    setRecipients(
                      recipients.map((row) =>
                        row.access_id === choice.id ? { ...row, can_complete: checked } : row,
                      ),
                    )
                  }
                  disabled={busy}
                />
              )}
            </div>
          )
        })
      )}
      {recurring && (
        <Checkbox
          label={t('Auch folgende Ausgaben im Mitgliederbereich freigeben')}
          checked={following}
          onChange={setFollowing}
          disabled={busy}
        />
      )}
      {data.claimed_by && <p>{t('Dieses Angebot wurde bereits übernommen.')}</p>}
      <button
        type="button"
        className="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true)
          setError(null)
          try {
            const saved = await api.put<Publication>(endpoint, {
              version: version.current,
              ...values,
            })
            setBaseline(JSON.stringify(values))
            version.current = saved.version
            onSaved()
          } catch (err) {
            setError(errorMessage(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        {t('Mitgliederfreigabe speichern')}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
