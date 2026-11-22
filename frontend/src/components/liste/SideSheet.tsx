// Seitenblatt (Web-Oberfläche W11): ein Eintrag einer Liste rechts daneben, ohne die Liste zu
// verlassen. Nicht modal; Escape oder „Schließen“ macht es zu, der Fokus geht zurück zur Zeile.
import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { t } from '../../i18n/index.ts'

export function SideSheet({
  title,
  subtitle,
  onClose,
  actions,
  children,
}: {
  title: ReactNode
  subtitle?: ReactNode
  onClose: () => void
  /** Knöpfe am Fuß, z. B. „Akte öffnen“ */
  actions?: ReactNode
  children: ReactNode
}) {
  const id = useId()
  const heading = useRef<HTMLHeadingElement>(null)
  const back = useRef<Element | null>(null)
  useEffect(() => {
    back.current = document.activeElement
    heading.current?.focus()
    return () => {
      if (back.current instanceof HTMLElement && back.current.isConnected) back.current.focus()
    }
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <aside className="side-sheet" role="dialog" aria-labelledby={id}>
      <div className="side-sheet-head">
        <div>
          <h2 id={id} ref={heading} tabIndex={-1}>
            {title}
          </h2>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        <button
          type="button"
          className="button button-ghost side-sheet-close"
          aria-label={t('Schließen')}
          onClick={onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <div className="side-sheet-body">{children}</div>
      {actions && <div className="side-sheet-actions">{actions}</div>}
    </aside>
  )
}
