import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { t } from '../../i18n/index.ts'
import './music.css'

/** Rahmen der Musikseiten; die Unterpunkte stehen in der Seitenleiste (Menüprüfung M-08). */
export function MusicLayout({ children }: { children: ReactNode }) {
  return <div className="music-workspace stack">{children}</div>
}

export function MusicHeader({
  title,
  description,
  context,
}: {
  title: string
  description?: string
  context?: string
}) {
  return (
    <header className="music-page-header">
      {context && (
        <p className="music-breadcrumb">
          <Link to="/musik">{t('Auftritte')}</Link>
          <span aria-hidden="true"> / </span>
          {context}
        </p>
      )}
      <h1>{title}</h1>
      {description && <p className="muted">{description}</p>}
    </header>
  )
}

export function MusicEmptyState({ children }: { children?: ReactNode }) {
  return <p className="music-empty">{children || t('Noch keine Einträge vorhanden.')}</p>
}

export function MusicStatus({ status }: { status: string }) {
  return (
    <span className={`music-status music-status-${status}`}>
      {status === 'accepted'
        ? t('Zugesagt')
        : status === 'declined'
          ? t('Abgesagt')
          : t('Angefragt')}
    </span>
  )
}
