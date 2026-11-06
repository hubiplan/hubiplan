// Startseiten-Kachel „Zu erledigen“: Aufgaben, Freigaben, Anfragen, überfällige Rechnungen.
import { Link } from 'react-router-dom'
import { orgApi } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { LoadError } from './ui.tsx'
import { useLoad } from './forms.ts'
import { t } from '../i18n/index.ts'
import { api } from '../api/client.ts'
import { useState } from 'react'
import { errorMessage } from './forms.ts'
import { TaskTileRow } from './TaskTileRow.tsx'
import '../pages/todos.css'

export function OpenTasksTile({ org }: { org: OrgSummary }) {
  const { data, error, reload } = useLoad(() => orgApi.openTasks(org.id), [org.id])
  const items = data?.items ?? []
  const [actionError, setActionError] = useState<string | null>(null)
  return (
    <div className="card tile task-overview tile-wide">
      <div className="task-overview-head">
        <h2>
          {t('Zu erledigen')}
          {items.length > 0 && <span className="badge">{items.length}</span>}
        </h2>
      </div>
      {actionError && <p role="alert">{actionError}</p>}
      {error && (
        <LoadError message={t('Was zu erledigen ist, ließ sich nicht laden.')} onRetry={reload} />
      )}
      {data && items.length === 0 && <p className="muted">{t('Nichts zu erledigen.')}</p>}
      {items.length > 0 && (
        <ul className="plain-list task-overview-list">
          {items.map((tm, i) => (
            <TaskTileRow
              key={`${tm.kind}-${i}`}
              title={tm.title}
              link={tm.link}
              kind={tm.kind_label}
              detail={tm.detail}
              due={tm.highlight ? tm.due_label : undefined}
              overdue={tm.highlight && tm.overdue}
              onComplete={
                tm.kind === 'todo' && tm.can_edit
                  ? () => {
                      void api
                        .patch(`/api/orgs/${org.id}/todos/${tm.ref}/`, {
                          status: 'done',
                          version: tm.version,
                        })
                        .then(() => reload())
                        .catch((err: unknown) => setActionError(errorMessage(err)))
                    }
                  : undefined
              }
            />
          ))}
        </ul>
      )}
      {org.permissions.includes('todos.view') && (
        <div className="home-tile-actions">
          <Link className="button button-primary" to={`/aufgaben?einheit=${org.id}&neu=1`}>
            <span aria-hidden="true">+</span> {t('Neue Aufgabe')}
          </Link>
          <Link to={`/aufgaben?einheit=${org.id}`}>{t('Alle Aufgaben')}</Link>
        </div>
      )}
    </div>
  )
}
