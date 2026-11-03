import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { todoApi, todoBase } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { errorMessage, useAutoSave, useForm, useLoad } from '../components/forms.ts'
import { Field, LoadError, SaveStatus, SelectField } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'
import { TodoSharing } from '../components/TodoSharing.tsx'

export function TodosPage() {
  const { active, activeDept, can } = useOrg()
  const base = todoBase(active?.id ?? null, activeDept?.id)
  if (!can('todos.view')) return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  return <TodoWorkspace key={base} base={base} />
}

function TodoWorkspace({ base }: { base: string }) {
  const [tab, setTab] = useState('open')
  const [filter, setFilter] = useState('all')
  const [newTask, setNewTask] = useState(false)
  const [params, setParams] = useSearchParams()
  const { data, error, reload } = useLoad(() => todoApi.list(base, tab === 'trash'), [base, tab])
  const [actionError, setActionError] = useState<string | null>(null)
  const selected = data?.items.find((item) => String(item.id) === params.get('aufgabe'))
  const items = (data?.items ?? []).filter(
    (item) =>
      (tab === 'trash' || item.status === tab) &&
      (filter === 'all' ||
        (filter === 'mine' && !item.shared) ||
        (filter === 'shared' && item.shared) ||
        (filter === 'overdue' &&
          !!item.due_date &&
          item.due_date < new Date().toLocaleDateString('en-CA'))),
  )
  async function change(item: Todo, changes: object) {
    try {
      setActionError(null)
      await todoApi.update(base, item.id, { version: item.version, ...changes })
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
            setNewTask(true)
            setParams({})
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
              setTab(key)
              setNewTask(false)
              setParams({})
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
        <option value="overdue">{t('Überfällig')}</option>
      </SelectField>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {newTask && (
        <TodoEditor
          key="new"
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
      {selected?.can_share && tab !== 'trash' && (
        <TodoSharing
          key={`share-${selected.id}-${selected.version}`}
          base={base}
          todo={selected}
          onSaved={() => void reload()}
        />
      )}
      <ul className="plain-list task-list">
        {items.map((item) => (
          <li key={item.id}>
            {tab !== 'trash' && (
              <input
                type="checkbox"
                aria-label={t('Erledigt')}
                checked={item.status === 'done'}
                disabled={!item.can_edit}
                onChange={(event) =>
                  void change(item, { status: event.target.checked ? 'done' : 'open' })
                }
              />
            )}
            <button
              className="button button-ghost"
              onClick={() => {
                setNewTask(false)
                setParams({ aufgabe: String(item.id) })
              }}
            >
              {item.title}
            </button>
            <span className="muted">{item.due_date ?? t('ohne Frist')}</span>
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
      <a className="button button-ghost" href="/api/me/todos/export/">
        {t('Eigene Aufgaben exportieren')}
      </a>
    </section>
  )
}

function TodoEditor({ base, todo, onSaved }: { base: string; todo?: Todo; onSaved: () => void }) {
  const version = useRef(todo?.version ?? 1)
  const form = useForm({
    title: todo?.title ?? '',
    description: todo?.description ?? '',
    due_date: todo?.due_date ?? '',
    due_time: todo?.due_time?.slice(0, 5) ?? '',
  })
  const writable = !todo || todo.can_edit
  const payload = () => ({
    ...form.values,
    due_date: form.values.due_date || null,
    due_time: form.values.due_date ? form.values.due_time || null : null,
  })
  const auto = useAutoSave(
    form,
    async () => {
      const updated = await todoApi.update(base, todo!.id, {
        ...payload(),
        version: version.current,
      })
      version.current = updated.version
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
            await todoApi.create(base, payload())
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
