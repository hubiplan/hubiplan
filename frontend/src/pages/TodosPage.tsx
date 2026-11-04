import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { TodoEventLink } from '../components/TodoEventLink.tsx'
import { todoApi, todoBase } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { errorMessage, useAutoSave, useForm, useLoad } from '../components/forms.ts'
import { Field, LoadError, SaveStatus, SelectField } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'
import { TodoSharing } from '../components/TodoSharing.tsx'
import { TodoOwnership } from '../components/TodoOwnership.tsx'
import { OrphanTasks } from '../components/OrphanTasks.tsx'
import { useAuth } from '../auth/AuthContext.tsx'
import { TodoReminders } from '../components/TodoReminders.tsx'
import { TodoAttachments } from '../components/TodoAttachments.tsx'
import { followingChoice, TodoSeries } from '../components/TodoSeries.tsx'
import { TodoLocalNote, TodoProgress } from '../components/TodoDistribution.tsx'
import { TodoCleanup } from '../components/TodoCleanup.tsx'
import './todos.css'
import { confirmLeave, useDraftGuard, useGuarded } from '../components/leaveGuard.ts'

export function TodosPage() {
  const { active, activeDept, activeKey, orgs, departments, select } = useOrg()
  const [params, setParams] = useSearchParams()
  const target = params.get('abteilung') ? `d:${params.get('abteilung')}` : params.get('einheit')
  const knownTarget =
    !!target &&
    (target.startsWith('d:')
      ? departments.some((dept) => `d:${dept.id}` === target)
      : orgs.some((org) => String(org.id) === target))
  useEffect(() => {
    if (!knownTarget || target === activeKey) return
    let alive = true
    void confirmLeave().then((allowed) => {
      if (!alive) return
      if (allowed) select(target!)
      else {
        const next = new URLSearchParams(params)
        next.delete('abteilung')
        next.delete('einheit')
        setParams(next, { replace: true })
      }
    })
    return () => {
      alive = false
    }
  }, [target, knownTarget, activeKey, select, params, setParams])
  const base = todoBase(active?.id ?? null, activeDept?.id)
  if (!(active?.permissions ?? activeDept?.permissions ?? []).includes('todos.view'))
    return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  return <TodoWorkspace key={base} base={base} />
}

function TodoWorkspace({ base }: { base: string }) {
  const guard = useGuarded()
  const { user } = useAuth()
  const { active, activeDept } = useOrg()
  const can = (permission: string) =>
    (active?.permissions ?? activeDept?.permissions ?? []).includes(permission)
  const [tab, setTab] = useState('open')
  const [filter, setFilter] = useState('all')
  const [newTask, setNewTask] = useState(
    () => new URLSearchParams(location.search).get('neu') === '1',
  )
  const [params, setParams] = useSearchParams()
  const { data, error, reload } = useLoad(() => todoApi.list(base, tab === 'trash'), [base, tab])
  const [actionError, setActionError] = useState<string | null>(null)
  const selected = data?.items.find((item) => String(item.id) === params.get('aufgabe'))
  const items = (data?.items ?? []).filter(
    (item) =>
      (tab === 'trash' || item.status === tab) &&
      (!params.get('termin') || String(item.event?.id) === params.get('termin')) &&
      (filter === 'all' ||
        (filter === 'mine' && !item.shared) ||
        (filter === 'shared' && item.shared && item.created_by !== user?.id) ||
        (filter === 'sent' && item.shared && item.created_by === user?.id) ||
        (filter === 'overdue' && item.overdue)),
  )
  async function change(item: Todo, changes: object) {
    if (!(await confirmLeave())) return
    try {
      setActionError(null)
      const current = tab === 'trash' ? item : await todoApi.get(base, item.id)
      await todoApi.update(base, item.id, { version: current.version, ...changes })
      await reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <section>
      <div className="page-heading">
        <h1>{t('Aufgaben')}</h1>
        <button
          className="button"
          onClick={() => {
            void guard(() => {
              setNewTask(true)
              setParams({})
            })
          }}
        >
          {t('Neue Aufgabe')}
        </button>
      </div>
      <div className="button-row" role="group" aria-label={t('Aufgaben')}>
        {(['open', 'done', 'trash'] as const).map((key) => (
          <button
            key={key}
            className="button button-ghost"
            aria-pressed={tab === key}
            onClick={() => {
              void guard(() => {
                setTab(key)
                setNewTask(false)
                setParams({})
              })
            }}
          >
            {t(key === 'open' ? 'Offen' : key === 'done' ? 'Erledigt' : 'Papierkorb')}
          </button>
        ))}
      </div>
      <SelectField
        label={t('Filter')}
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      >
        <option value="all">{t('Alle Aufgaben')}</option>
        <option value="mine">{t('Meine')}</option>
        <option value="shared">{t('Geteilt mit mir')}</option>
        <option value="sent">{t('Von mir geteilt')}</option>
        <option value="overdue">{t('Überfällig')}</option>
      </SelectField>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {can('todos.edit') && can('roles.edit') && <TodoCleanup base={base} />}
      {can('todos.edit') && can('roles.edit') && (
        <OrphanTasks base={base} onSaved={() => void reload()} />
      )}
      {newTask && (
        <TodoEditor
          key="new"
          initialEvent={Number(params.get('termin')) || undefined}
          base={base}
          onSaved={() => {
            setNewTask(false)
            void reload()
          }}
        />
      )}
      {selected && tab !== 'trash' && (
        <TodoEditor key={selected.id} base={base} todo={selected} onSaved={() => void reload()} />
      )}
      {selected && tab !== 'trash' && (
        <TodoEventLink base={base} todo={selected} onSaved={() => void reload()} />
      )}
      {selected && (selected.due_date || selected.series) && (
        <TodoSeries
          key={`series-${selected.id}-${selected.series?.id ?? 'new'}`}
          base={base}
          todo={selected}
          trash={tab === 'trash'}
          onSaved={() => void reload()}
        />
      )}
      {selected?.due_date && tab !== 'trash' && (
        <TodoReminders key={`remind-${selected.id}`} base={base} id={selected.id} />
      )}
      {selected?.distributed && tab !== 'trash' && (
        <TodoLocalNote
          key={`local-${selected.id}`}
          base={base}
          todo={selected}
          onSaved={() => void reload()}
        />
      )}
      {selected?.per_unit && tab !== 'trash' && (
        <TodoProgress
          key={`progress-${selected.id}`}
          base={base}
          id={selected.id}
          recurring={!!selected.series}
        />
      )}
      {selected && tab !== 'trash' && (
        <TodoAttachments
          key={`files-${selected.id}`}
          base={base}
          id={selected.id}
          writable={selected.can_edit}
          recurring={!!selected.series}
          onSaved={() => void reload()}
        />
      )}
      {selected?.can_share && tab !== 'trash' && (
        <TodoSharing
          key={`share-${selected.id}`}
          base={base}
          todo={selected}
          onSaved={() => void reload()}
        />
      )}
      {selected && !!selected.owners?.length && tab !== 'trash' && (
        <TodoOwnership
          key={`owner-${selected.id}`}
          base={base}
          todo={selected}
          onSaved={() => void reload()}
        />
      )}
      <ul className="plain-list task-list">
        {items.map((item) => (
          <li
            key={item.id}
            className={
              item.highlight
                ? `task-reminder${item.overdue ? ' task-reminder-overdue' : ''}`
                : undefined
            }
          >
            {tab !== 'trash' && (
              <input
                type="checkbox"
                aria-label={t('Erledigt')}
                checked={item.status === 'done'}
                disabled={!item.can_edit || item.can_complete === false}
                onChange={(event) =>
                  void change(item, { status: event.target.checked ? 'done' : 'open' })
                }
              />
            )}
            <button
              className="button button-ghost"
              onClick={() => {
                void guard(() => {
                  setNewTask(false)
                  setParams({ aufgabe: String(item.id) })
                })
              }}
            >
              {item.title}
            </button>
            <span className="muted">{item.due_date ?? t('ohne Frist')}</span>
            {item.highlight && <span className="badge">{item.due_label}</span>}
            {item.can_delete && (
              <button
                className="button button-ghost"
                onClick={() => void change(item, { deleted: tab !== 'trash' })}
              >
                {t(tab === 'trash' ? 'Wiederherstellen' : 'Löschen')}
              </button>
            )}
          </li>
        ))}
      </ul>
      {data && !items.length && <p className="muted">{t('Keine Aufgaben vorhanden.')}</p>}
      <a className="button button-ghost" href="/api/me/todos/export/?files=1">
        {t('Eigene Aufgaben exportieren')}
      </a>
    </section>
  )
}

function todoFields(todo?: Todo) {
  return {
    title: todo?.title ?? '',
    description: todo?.description ?? '',
    due_date: todo?.due_date ?? '',
    due_time: todo?.due_time?.slice(0, 5) ?? '',
  }
}

function TodoEditor({
  base,
  todo,
  initialEvent,
  onSaved,
}: {
  base: string
  todo?: Todo
  initialEvent?: number
  onSaved: () => void
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
            await todoApi.create(base, {
              ...payload(),
              ...(initialEvent ? { event: initialEvent } : {}),
            })
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
      <details open={!!todo}>
        {todo?.central_readonly && (
          <p className="muted">
            {t('Titel, Beschreibung und Frist werden von der Quelle vorgegeben.')}
          </p>
        )}
        <summary>{t('Beschreibung und Frist')}</summary>
        <label>
          {t('Beschreibung')}
          <textarea
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
