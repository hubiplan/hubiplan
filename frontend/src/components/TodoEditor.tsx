import { useEffect, useRef } from 'react'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { useAutoSave, useForm } from './forms.ts'
import { Field, SaveStatus } from './ui.tsx'
import { followingChoice } from './TodoSeries.tsx'
import { useDraftGuard } from './leaveGuard.ts'
import { t } from '../i18n/index.ts'

function todoFields(todo?: Todo) {
  return {
    title: todo?.title ?? '',
    description: todo?.description ?? '',
    due_date: todo?.due_date ?? '',
    due_time: todo?.due_time?.slice(0, 5) ?? '',
  }
}

export function TodoEditor({
  base,
  todo,
  initialEvent,
  onSaved,
  extraValues,
  onCreated,
}: {
  base: string
  todo?: Todo
  initialEvent?: number
  onSaved: () => void
  extraValues?: object
  onCreated?: (todo: Todo) => void
}) {
  const version = useRef(todo?.version ?? 1)
  const baseline = useRef(todoFields(todo))
  const form = useForm(todoFields(todo))
  useEffect(() => {
    // Statuswechsel dürfen die eigene Versionsbasis vorziehen, externe Inhaltsänderungen nicht.
    if (todo && JSON.stringify(todoFields(todo)) === JSON.stringify(baseline.current))
      version.current = todo.version
  }, [todo])
  useDraftGuard(!todo && Object.values(form.values).some(Boolean), () =>
    form.setValues(todoFields()),
  )
  const writable = !todo || (todo.can_edit && !todo.central_readonly)
  const payload = () => ({
    ...form.values,
    due_date: form.values.due_date || null,
    due_time: form.values.due_date ? form.values.due_time || null : null,
  })
  const auto = useAutoSave(
    form,
    async (changes) => {
      const following = todo?.series ? await followingChoice() : false
      if (following === null) throw new Error(t('Änderung wurde nicht gespeichert.'))
      const update: Record<string, unknown> = { ...changes }
      if ('due_date' in update) {
        update.due_date = update.due_date || null
        if (!update.due_date) update.due_time = null
      }
      if ('due_time' in update) update.due_time = update.due_time || null
      const updated = await todoApi.update(base, todo!.id, {
        ...update,
        following,
        version: version.current,
      })
      version.current = updated.version
      baseline.current = todoFields(updated)
      onSaved()
    },
    { enabled: !!todo && writable },
  )
  return (
    <form
      className="card"
      onSubmit={(event) => {
        event.preventDefault()
        if (!todo)
          void form.submit(async () => {
            const created = await todoApi.create(base, {
              ...extraValues,
              ...payload(),
              ...(initialEvent ? { event: initialEvent } : {}),
            })
            form.setValues(todoFields())
            onCreated?.(created)
            onSaved()
          })
      }}
    >
      <Field
        label={t('Titel')}
        required
        maxLength={200}
        value={form.values.title}
        disabled={!writable}
        error={form.errors.title}
        onChange={(event) => form.set('title', event.target.value)}
      />
      <details open>
        {todo?.central_readonly && (
          <p className="muted">
            {t('Titel, Beschreibung und Frist werden von der Quelle vorgegeben.')}
          </p>
        )}
        <summary>{t('Beschreibung und Frist')}</summary>
        <label>
          {t('Beschreibung')}
          <textarea
            rows={8}
            maxLength={50000}
            value={form.values.description}
            disabled={!writable}
            onChange={(event) => form.set('description', event.target.value)}
          />
        </label>
        <Field
          label={t('Frist')}
          type="date"
          value={form.values.due_date}
          disabled={!writable}
          error={form.errors.due_date}
          onChange={(event) => form.set('due_date', event.target.value)}
        />
        <Field
          label={t('Uhrzeit')}
          type="time"
          value={form.values.due_time}
          disabled={!writable || !form.values.due_date}
          error={form.errors.due_time}
          onChange={(event) => form.set('due_time', event.target.value)}
        />
      </details>
      {todo ? (
        <SaveStatus auto={auto} />
      ) : (
        <button className="button" disabled={form.busy}>
          {t('Anlegen')}
        </button>
      )}
      {form.message && <p role="status">{form.message.text}</p>}
    </form>
  )
}
