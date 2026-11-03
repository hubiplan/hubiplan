import { useState } from 'react'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import type { Todo, TodoShare } from '../api/todos.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function TodoSharing({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const { data, error, reload } = useLoad(
    () =>
      api.get<{ users: { id: number; name: string }[]; roles: { id: number; name: string }[] }>(
        `${base}choices/`,
      ),
    [base],
  )
  const [shares, setShares] = useState<TodoShare[]>(todo.shares ?? [])
  const [recipient, setRecipient] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  function update(index: number, patch: Partial<TodoShare>) {
    setShares(shares.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }
  async function save() {
    setBusy(true)
    try {
      await todoApi.update(base, todo.id, { version: todo.version, shares })
      onSaved()
      setMessage(t('Gespeichert.'))
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card">
      <h2>{t('Teilen mit')}</h2>
      {error && <LoadError message={error} onRetry={reload} />}
      {data && (
        <>
          <SelectField
            label={t('Empfänger')}
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
          >
            <option value="">{t('Bitte wählen')}</option>
            <optgroup label={t('Personen')}>
              {data.users.map((u) => (
                <option key={u.id} value={`u:${u.id}`}>
                  {u.name}
                </option>
              ))}
            </optgroup>
            <optgroup label={t('Rollen')}>
              {data.roles.map((r) => (
                <option key={r.id} value={`r:${r.id}`}>
                  {r.name}
                </option>
              ))}
            </optgroup>
          </SelectField>
          <button
            className="button button-ghost"
            disabled={!recipient}
            onClick={() => {
              const [kind, id] = recipient.split(':')
              setShares([
                ...shares,
                {
                  ...(kind === 'u' ? { user: Number(id) } : { role: Number(id) }),
                  level: 'view',
                  responsible: false,
                },
              ])
              setRecipient('')
            }}
          >
            {t('Hinzufügen')}
          </button>
          {shares.map((entry, index) => (
            <div className="subcard" key={`${entry.user ?? 'r'}:${entry.role ?? 'u'}:${index}`}>
              <p>
                {entry.user
                  ? data.users.find((u) => u.id === entry.user)?.name
                  : data.roles.find((r) => r.id === entry.role)?.name}
              </p>
              <SelectField
                label={t('Berechtigung')}
                value={entry.level}
                onChange={(event) =>
                  update(index, { level: event.target.value as 'view' | 'edit' })
                }
              >
                <option value="view">{t('Lesen')}</option>
                <option value="edit">{t('Bearbeiten')}</option>
              </SelectField>
              <Checkbox
                label={t('Zuständig')}
                checked={entry.responsible}
                onChange={(value) => update(index, { responsible: value })}
              />
              <button
                className="button button-ghost"
                onClick={() => setShares(shares.filter((_, i) => i !== index))}
              >
                {t('Entfernen')}
              </button>
            </div>
          ))}
          <button className="button" disabled={busy} onClick={() => void save()}>
            {t('Freigaben speichern')}
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
