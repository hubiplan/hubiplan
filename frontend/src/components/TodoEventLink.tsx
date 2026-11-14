import { Link } from 'react-router-dom'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import type { Todo } from '../api/todos.ts'
import { useOptionalOrg } from '../org/OrgContext.tsx'
import { t } from '../i18n/index.ts'
import { errorMessage, useLoad } from './forms.ts'
import { useState } from 'react'

export function TodoEventLink({
  base,
  todo,
  onSaved,
}: {
  base: string
  todo: Todo
  onSaved: () => void
}) {
  const { data } = useLoad(
    () => api.get<{ items: { id: number; title: string; starts_at: string }[] }>(`${base}events/`),
    [base],
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <section className="card">
      <h2>{t('Terminverknüpfung')}</h2>
      <p>
        {todo.event?.available
          ? todo.event.title
          : todo.event
            ? t('Termin nicht verfügbar')
            : t('Ohne Terminverknüpfung')}
      </p>
      {todo.can_delete && (
        <label>
          {t('Termin')}
          <select
            disabled={busy}
            value={todo.event?.id ?? ''}
            onChange={async (event) => {
              const id = Number(event.target.value) || null
              setBusy(true)
              setError(null)
              try {
                await todoApi.update(base, todo.id, { version: todo.version, event: id })
                onSaved()
              } catch (err) {
                setError(errorMessage(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            <option value="">{t('Ohne Terminverknüpfung')}</option>
            {data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {item.starts_at.slice(0, 10)}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="muted">
        {t(
          'Die Verknüpfung ändert weder Frist noch Freigaben. Bei einer Terminserie gilt sie für die ganze Terminserie.',
        )}
      </p>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

export function EventTaskLink({ base, eventId }: { base: string; eventId: number }) {
  const context = useOptionalOrg()
  const active = context?.active
  const activeDept = context?.activeDept
  const match = base.match(/^\/api\/(orgs|depts)\/(\d+)\/(?:events\/?)?$/)
  if (!match) return null
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  if (!permissions.includes('todos.view')) return null
  const query = new URLSearchParams({ termin: String(eventId) })
  query.set(match[1] === 'depts' ? 'abteilung' : 'einheit', match[2])
  // Anlegen als Knopf, Anzeigen als Verweis (Ralf 14.11.2026: zwei Verweise nebeneinander
  // lasen sich wie ein Satz)
  return (
    <p className="button-row">
      <Link className="button" to={`/aufgaben?${query}&neu=1`}>
        <span aria-hidden="true">+</span> {t('Aufgabe zu diesem Termin anlegen')}
      </Link>
      <Link to={`/aufgaben?${query}`}>{t('Aufgaben zu diesem Termin anzeigen')}</Link>
    </p>
  )
}
