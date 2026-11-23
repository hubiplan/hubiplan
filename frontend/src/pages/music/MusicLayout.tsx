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

export type UniformDetails = {
  id: number
  name: string
  description: string
  checklist: string[]
  has_image: boolean
} | null

/** Uniform für Eingeteilte: Name mit Ergänzung, Beschreibung, Checkliste, Bild (Issue #712) */
export function UniformInfo({
  text,
  details,
  imageUrl,
}: {
  text: string
  details?: UniformDetails
  imageUrl?: string
}) {
  if (!text) return null
  return (
    <div>
      <dt>{t('Uniform')}</dt>
      <dd className="stack">
        <span>{text}</span>
        {!!details?.description && <span className="muted">{details.description}</span>}
        {!!details?.checklist.length && (
          <ul className="music-checklist" aria-label={t('Was dazugehört')}>
            {details.checklist.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}
        {details?.has_image && imageUrl && (
          <img className="music-uniform-image" src={imageUrl} alt={details.name} />
        )}
      </dd>
    </div>
  )
}
