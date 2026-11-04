import { Link } from 'react-router-dom'
import { todoApi, todoBase } from '../api/todos.ts'
import { useLoad } from './forms.ts'
import { LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { useState } from 'react'
import { errorMessage } from './forms.ts'
import { TaskTileRow } from './TaskTileRow.tsx'
import { formatDate } from './forms.ts'
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
    <div className="card tile task-overview">
      <div className="task-overview-head">
        <h2>
          {t('Offene Aufgaben')} <span className="badge">{open.length}</span>
        </h2>
        <Link className="button" to={`/aufgaben?abteilung=${department}`}>
          {t('Alle Aufgaben')}
        </Link>
      </div>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      <ul className="plain-list task-overview-list">
        {shown.map((item) => (
          <TaskTileRow
            key={item.id}
            title={item.title}
            link={`/aufgaben?abteilung=${department}&aufgabe=${item.id}`}
            kind={t('Aufgabe')}
            detail={item.due_date ? formatDate(item.due_date) : t('ohne Frist')}
            due={item.highlight ? item.due_label : undefined}
            overdue={item.highlight && item.overdue}
            onComplete={
              item.can_edit
                ? () => {
                    void todoApi
                      .update(todoBase(null, department), item.id, {
                        status: 'done',
                        version: item.version,
                      })
                      .then(() => reload())
                      .catch((err: unknown) => setActionError(errorMessage(err)))
                  }
                : undefined
            }
          />
        ))}
      </ul>
    </div>
  )
}
