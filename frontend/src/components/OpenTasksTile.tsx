// Startseiten-Kachel „Offene Aufgaben“: Vorgänge, die eine Entscheidung brauchen.
import { Link } from 'react-router-dom'
import { orgApi } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { LoadError } from './ui.tsx'
import { useLoad } from './forms.ts'
import { t } from '../i18n/index.ts'
import { api } from '../api/client.ts'
import { useState } from 'react'
import { errorMessage } from './forms.ts'
import '../pages/todos.css'

export function OpenTasksTile({ org }: { org: OrgSummary }) {
  const { data, error, reload } = useLoad(() => orgApi.openTasks(org.id), [org.id])
  const items = data?.items ?? []
  const [actionError, setActionError] = useState<string | null>(null)
  return (
    <div className="card tile">
      <h2>
        {t('Offene Aufgaben')}
        {items.length > 0 && <span className="badge"> {items.length}</span>}
      </h2>
      {org.permissions.includes('todos.view') && <Link to="/aufgaben">{t('Neue Aufgabe')}</Link>}
      {actionError && <p role="alert">{actionError}</p>}
      {error && (
        <LoadError
          message={t('Die offenen Aufgaben konnten nicht geladen werden.')}
          onRetry={reload}
        />
      )}
      {data && items.length === 0 && (
        <p className="muted">{t('Zurzeit ist nichts zu entscheiden.')}</p>
      )}
      {items.length > 0 && (
        <ul className="plain-list task-list">
          {items.map((tm, i) => (
            <li
              key={`${tm.kind}-${i}`}
              className={
                tm.highlight
                  ? `task-reminder${tm.overdue ? ' task-reminder-overdue' : ''}`
                  : undefined
              }
            >
              {tm.kind === 'todo' && tm.can_edit && (
                <input
                  type="checkbox"
                  aria-label={t('Erledigt')}
                  checked={false}
                  onChange={() => {
                    void api
                      .patch(`/api/orgs/${org.id}/todos/${tm.ref}/`, {
                        status: 'done',
                        version: tm.version,
                      })
                      .then(() => reload())
                      .catch((err: unknown) => setActionError(errorMessage(err)))
                  }}
                />
              )}
              <span className="muted small">{tm.kind_label}</span>
              {tm.highlight && <span className="badge">{tm.due_label}</span>}
              <div>
                <Link to={tm.link}>{tm.title}</Link>
                <span className="muted small"> · {tm.detail}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
