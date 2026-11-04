import { Link } from 'react-router-dom'
import { t } from '../i18n/index.ts'

/** Gemeinsame Zeile der Aufgaben-Kacheln für Einheit und Abteilung. */
export function TaskTileRow({
  title,
  link,
  kind,
  detail,
  due,
  overdue,
  onComplete,
}: {
  title: string
  link: string
  kind: string
  detail?: string
  due?: string
  overdue?: boolean
  onComplete?: () => void
}) {
  return (
    <li className={`task-overview-row${overdue ? ' task-overview-row-overdue' : ''}`}>
      {onComplete && (
        <label className="task-overview-check" title={t('Erledigt')}>
          <input
            type="checkbox"
            checked={false}
            aria-label={`${t('Erledigt')}: ${title}`}
            onChange={onComplete}
          />
        </label>
      )}
      <div className="task-overview-content">
        <div className="task-overview-meta">
          <span>{kind}</span>
          {due && <span className="task-overview-due">{due}</span>}
        </div>
        <Link className="task-overview-title" to={link}>
          {title}
        </Link>
        {detail && <p className="task-overview-detail">{detail}</p>}
      </div>
    </li>
  )
}
