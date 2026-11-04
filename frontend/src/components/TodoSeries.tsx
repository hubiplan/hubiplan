import { useState } from 'react'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { choiceDialog, confirmDialog } from './dialog.ts'
import { errorMessage } from './forms.ts'
import { confirmLeave, flushAllForms, useDraftGuard } from './leaveGuard.ts'
import { Checkbox, Field, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

export async function followingChoice(): Promise<boolean | null> {
  const result = await choiceDialog({
    title: t('Nur diese Aufgabe oder auch alle folgenden?'),
    choices: [
      { value: 'one', label: t('Nur diese Aufgabe') },
      { value: 'following', label: t('Auch alle folgenden'), primary: true },
      { value: 'cancel', label: t('Abbrechen') },
    ],
    cancelValue: 'cancel',
  })
  return result === 'cancel' ? null : result === 'following'
}

export function TodoSeries({
  base,
  todo,
  trash,
  onSaved,
}: {
  base: string
  todo: Todo
  trash: boolean
  onSaved: () => void
}) {
  const [values, setValues] = useState({
    repeat: todo.series?.repeat ?? 'monthly',
    interval: String(todo.series?.interval ?? 1),
    basis: todo.series?.basis ?? 'due',
    last_day: todo.series?.last_day ?? false,
    ends_on: todo.series?.ends_on ?? '',
    count: String(todo.series?.count ?? ''),
  })
  const [initial, setInitial] = useState(JSON.stringify(values))
  const [baseVersion, setBaseVersion] = useState(todo.series?.version)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dirty = initial !== JSON.stringify(values)
  useDraftGuard(dirty, () => setValues(JSON.parse(initial)))

  async function change(patch: object, rules = false) {
    if (busy) return
    if (rules ? !(await flushAllForms()) : !(await confirmLeave())) return
    setBusy(true)
    setError(null)
    try {
      const current = trash ? todo : await todoApi.get(base, todo.id)
      if (rules && current.series?.version !== baseVersion)
        throw new Error(t('Die Aufgabe wurde inzwischen geändert. Bitte neu laden.'))
      const result = await api.patch<{ series: Todo['series'] }>(`${base}${todo.id}/series/`, {
        version: current.version,
        ...patch,
      })
      setBaseVersion(result.series?.version)
      setInitial(JSON.stringify(values))
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <details className="card">
      <summary>
        {t('Wiederholen')}
        {todo.series ? ` · ${t('Serienausgabe')} ${todo.series.sequence_no}` : ''}
      </summary>
      {error && <p role="alert">{error}</p>}
      {todo.can_edit && !trash && todo.status === 'open' && (
        <>
          <SelectField
            label={t('Wiederholregel')}
            value={values.repeat}
            onChange={(event) =>
              setValues({ ...values, repeat: event.target.value as typeof values.repeat })
            }
          >
            <option value="daily">{t('täglich')}</option>
            <option value="weekly">{t('wöchentlich')}</option>
            <option value="monthly">{t('monatlich')}</option>
            <option value="yearly">{t('jährlich')}</option>
          </SelectField>
          <Field
            label={t('Alle n Zeiträume')}
            type="number"
            min={1}
            max={365}
            value={values.interval}
            onChange={(event) => setValues({ ...values, interval: event.target.value })}
          />
          <SelectField
            label={t('Nächste Frist ab')}
            value={values.basis}
            onChange={(event) =>
              setValues({ ...values, basis: event.target.value as 'due' | 'done' })
            }
          >
            <option value="due">{t('Alter Frist')}</option>
            <option value="done">{t('Erledigung')}</option>
          </SelectField>
          {values.repeat === 'monthly' && (
            <Checkbox
              label={t('Am letzten Tag des Monats')}
              checked={values.last_day}
              onChange={(value) => setValues({ ...values, last_day: value })}
            />
          )}
          <Field
            label={t('Serienende (optional)')}
            type="date"
            value={values.ends_on}
            onChange={(event) => setValues({ ...values, ends_on: event.target.value, count: '' })}
          />
          <Field
            label={t('Anzahl einschließlich erster Ausgabe (optional)')}
            type="number"
            min={1}
            max={10000}
            value={values.count}
            onChange={(event) => setValues({ ...values, count: event.target.value, ends_on: '' })}
          />
          <button
            className="button"
            disabled={busy}
            onClick={() =>
              void change(
                {
                  ...values,
                  interval: Number(values.interval),
                  count: values.count ? Number(values.count) : null,
                  ends_on: values.ends_on || null,
                  active: true,
                },
                true,
              )
            }
          >
            {t(todo.series ? 'Serienregel speichern' : 'Serie beginnen')}
          </button>
        </>
      )}
      {todo.series && (
        <>
          <p>
            {t(
              todo.series.active
                ? 'Die Serie wird beim Erledigen fortgesetzt.'
                : 'Die Serie ist beendet.',
            )}
          </p>
          {todo.can_edit && todo.series.active && !trash && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => void change({ active: false })}
            >
              {t('Serie beenden')}
            </button>
          )}
          {todo.can_delete && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => {
                void (async () => {
                  if (
                    await confirmDialog({
                      title: t(trash ? 'Ganze Serie wiederherstellen?' : 'Ganze Serie löschen?'),
                      message: t(
                        'Die Aktion betrifft die Serie einschließlich ihres Verlaufs und ihrer Anhänge.',
                      ),
                    })
                  )
                    await change({ deleted: !trash })
                })()
              }}
            >
              {t(trash ? 'Serie wiederherstellen' : 'Serie löschen')}
            </button>
          )}
        </>
      )}
    </details>
  )
}
