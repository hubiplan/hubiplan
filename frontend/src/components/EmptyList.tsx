// Leere Hauptliste mit nächstem Schritt (UX-Audit 16.11. VW-20): Wer anlegen darf, bekommt den
// Knopf der Hauptaktion direkt in der leeren Fläche; wer es nicht darf, liest, wer es kann.
import type { ReactNode } from 'react'
import { EmptyState } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function EmptyList({
  title,
  children,
  canAdd,
  action,
  link,
}: {
  /** z. B. „Noch keine Rücklagen.“ */
  title: string
  /** Erklärung, was hier entsteht */
  children?: ReactNode
  /** Die Person darf hier anlegen */
  canAdd: boolean
  /** Hauptaktion der Seite, derselbe Name wie der Knopf im Seitenkopf */
  action?: { label: string; onClick: () => void }
  /** Hauptaktion als eigene Seite; fertiges Element (Link) */
  link?: ReactNode
}) {
  return (
    <EmptyState
      title={title}
      action={
        canAdd
          ? (link ??
            (action && (
              <button type="button" className="button button-primary" onClick={action.onClick}>
                {action.label}
              </button>
            )))
          : undefined
      }
    >
      {children}
      {!canAdd && (
        <>
          {children ? ' ' : ''}
          {t('Anlegen kann, wer hier das Recht zum Bearbeiten hat.')}
        </>
      )}
    </EmptyState>
  )
}
