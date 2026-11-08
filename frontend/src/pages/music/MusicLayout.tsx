import type { ReactNode } from 'react'
import { PageHeader } from '../../components/PageHeader.tsx'
import { t } from '../../i18n/index.ts'
import './music.css'

/** Rahmen der Musikseiten; die Unterpunkte stehen in der Seitenleiste (Menüprüfung M-08). */
export function MusicLayout({ children }: { children: ReactNode }) {
  return <div className="music-workspace stack">{children}</div>
}

/**
 * Kopf einer Musikseite: einheitlicher Seitenkopf (S-05). Auf Seiten mit eigenem Menüpunkt
 * heißt die h1 wie der Menüpunkt (X-01); Unterseiten eines Auftritts (context) und Seiten
 * ohne Menüpunkt tragen ihren eigenen Titel.
 */
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
    <PageHeader
      title={context ? title : undefined}
      name={title}
      subtitle={context ?? description}
    />
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
