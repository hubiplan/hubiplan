// Eine Zeile im Block „Zu diesem Termin“: Bereich links, Stand in der Mitte, Knöpfe rechts.
// Leere Bereiche brauchen so nur eine Zeile (Ralf 15.11.2026, Terminansicht neu gegliedert).
import type { ReactNode } from 'react'

export function EventRow({
  label,
  children,
  actions,
  extra,
}: {
  label: string
  children?: ReactNode
  actions?: ReactNode
  /** Was sich unter der Zeile aufklappt, z. B. eine Auswahl */
  extra?: ReactNode
}) {
  return (
    <div className="event-row" role="group" aria-label={label}>
      <strong className="event-row-label">{label}</strong>
      <div className="event-row-body">{children}</div>
      {actions && <div className="button-row event-row-actions">{actions}</div>}
      {extra && <div className="event-row-extra">{extra}</div>}
    </div>
  )
}
