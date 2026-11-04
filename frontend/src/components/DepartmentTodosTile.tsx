import { Link } from 'react-router-dom'
import { todoApi, todoBase } from '../api/todos.ts'
import { useLoad } from './forms.ts'
import { LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { useState } from 'react'
import { errorMessage } from './forms.ts'
import '../pages/todos.css'

export function DepartmentTodosTile({ department }: { department: number }) {
  const { data, error, reload } = useLoad(
    () => todoApi.list(todoBase(null, department)),
    [department],
  )
  const open = (data?.items ?? []).filter((item) => item.status === 'open')
  const shown = [
    ...open.filter((item) => item.due_date),
    ...open.filter((item) => !item.due_date).slice(0, 5),
  ]
  const [actionError, setActionError] = useState<string | null>(null)
  return (
    <div className="card tile">
      <h2>
        {t('Offene Aufgaben')} <span className="badge">{open.length}</span>
      </h2>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      <Link to="/aufgaben">{t('Alle Aufgaben')}</Link>
      <ul className="plain-list">
        {shown.map((item) => (
          <li
            key={item.id}
            className={
              item.highlight
                ? `task-reminder${item.overdue ? ' task-reminder-overdue' : ''}`
                : undefined
            }
          >
            {item.can_edit && (
              <input
                type="checkbox"
                checked={false}
                aria-label={t('Erledigt')}
                onChange={() => {
                  void todoApi
                    .update(todoBase(null, department), item.id, {
                      status: 'done',
                      version: item.version,
                    })
                    .then(() => reload())
                    .catch((err: unknown) => setActionError(errorMessage(err)))
                }}
              />
            )}
            <Link to={`/aufgaben?aufgabe=${item.id}`}>{item.title}</Link>
            {item.highlight && <span className="badge">{item.due_label}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
