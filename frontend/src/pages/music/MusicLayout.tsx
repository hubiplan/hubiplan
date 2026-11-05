import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { t } from '../../i18n/index.ts'
import './music.css'
import { useActiveOrg } from '../../org/OrgContext.tsx'

export function MusicLayout({ children }: { children: ReactNode }) {
  const [params] = useSearchParams()
  const org = useActiveOrg()
  const area = params.get('ausstattung')
    ? 'equipment'
    : params.get('noten')
      ? 'scores'
      : params.get('proben')
        ? 'practice'
        : params.get('vorlagen')
          ? 'templates'
          : params.get('verfuegbarkeit')
            ? 'availability'
            : ['musicians', 'skills'].includes(params.get('art') || '')
              ? 'musicians'
              : 'performances'
  const items = [
    ['performances', '/musik', t('Auftritte')],
    ['musicians', '/musik?art=musicians', t('Musiker')],
    ['scores', '/musik?noten=1', t('Notenbestand')],
    ['practice', '/musik?proben=1', t('Proben und Notenausgabe')],
    ['availability', '/musik?verfuegbarkeit=1', t('Verfügbarkeiten')],
    ['templates', '/musik?vorlagen=1', t('Besetzungsvorlagen')],
    ...(org.modules.includes('material') && org.permissions.includes('material.view')
      ? [['equipment', '/musik?ausstattung=1', t('Instrumente und Uniformen')]]
      : []),
  ]
  return (
    <div className="music-workspace stack">
      <nav className="music-navigation" aria-label={t('Musikbereiche')}>
        <span className="music-navigation-label">{t('Musik')}</span>
        {items.map(([key, to, label]) => (
          <Link key={key} to={to} aria-current={area === key ? 'page' : undefined}>
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  )
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
