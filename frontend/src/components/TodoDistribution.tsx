import { useEffect, useRef } from 'react'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { formatDateTime, useAutoSave, useForm, useLoad } from './forms.ts'
import { LoadError, SaveStatus } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function TodoLocalNote({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const form = useForm({ local_note: todo.local_note ?? '' })
  const baseline = useRef(todo.local_note ?? '')
  const version = useRef(todo.version)
  useEffect(() => {
    if (todo.version < version.current) return
    if ((todo.local_note ?? '') === baseline.current) version.current = todo.version
    else if (form.values.local_note === baseline.current) {
      baseline.current = todo.local_note ?? ''
      version.current = todo.version
      form.setValues({ local_note: baseline.current })
    }
  }, [todo, form])
  const auto = useAutoSave(
    form,
    async (changes) => {
      const updated = await todoApi.update(base, todo.id, { ...changes, version: version.current })
      version.current = updated.version
      baseline.current = updated.local_note ?? ''
      onSaved()
    },
    { enabled: todo.can_edit },
  )
  return (
    <div className="card">
      <label>
        {t('Lokale Notiz')}
        <textarea
          value={form.values.local_note}
          disabled={!todo.can_edit}
          onChange={(event) => form.set('local_note', event.target.value)}
        />
      </label>
      <p className="muted">
        {t(
          'Diese Notiz und deine lokalen Anhänge bleiben in dieser Einheit. Die Quelle sieht nur den Fortschritt.',
        )}
      </p>
      <SaveStatus auto={auto} />
    </div>
  )
}

interface ProgressRow {
  unit: string
  sequence_no: number
  due_date: string | null
  status: string
  done_at: string | null
  done_by_id: number | null
  ended: boolean
  deleted: boolean
}

export function TodoProgress({
  base,
  id,
  recurring = false,
}: {
  base: string
  id: number
  recurring?: boolean
}) {
  const { data, error, reload } = useLoad(
    () => api.get<{ items: ProgressRow[] }>(`${base}${id}/progress/`),
    [base, id],
  )
  const sequences = [...new Set(data?.items.map((row) => row.sequence_no) ?? [])].sort(
    (a, b) => a - b,
  )
  return (
    <details className="card" open>
      <summary>{t('Fortschritt der Zieleinheiten')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      {sequences.map((sequence) => {
        const rows = data!.items.filter((row) => row.sequence_no === sequence)
        const done = rows.filter((row) => row.status === 'done' && !row.deleted).length
        return (
          <section key={sequence}>
            <h3>
              {recurring && (
                <>
                  {t('Serienausgabe')} {sequence} ·{' '}
                </>
              )}
              {t('{done} von {total} erledigt', { done, total: rows.length })}
            </h3>
            <ul className="plain-list">
              {rows.map((row, index) => (
                <li key={index}>
                  <strong>{row.unit}</strong> · {t('Lokale Frist')}:{' '}
                  {row.due_date ?? t('ohne Frist')} ·{' '}
                  {t(
                    row.deleted
                      ? 'Gelöscht'
                      : row.status === 'done'
                        ? 'Erledigt'
                        : row.ended
                          ? 'Beendet'
                          : 'Offen',
                  )}
                  {row.done_at && !row.deleted && (
                    <>
                      {' '}
                      · {formatDateTime(row.done_at)}
                      {row.done_by_id && <> · {t('Konto {id}', { id: row.done_by_id })}</>}
                    </>
                  )}
                  {row.ended && row.status === 'done' && !row.deleted && (
                    <> · {t('Serie beendet')}</>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
      <button className="button button-ghost" onClick={() => void reload()}>
        {t('Aktualisieren')}
      </button>
    </details>
  )
}
