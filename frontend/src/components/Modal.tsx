// Gemeinsamer modaler Dialog für größere Inhalte (z. B. Termine).
//
// Fokus bleibt im Dialog (Tab/Umschalt+Tab), die Seite dahinter ist für Tastatur
// und Screenreader gesperrt (inert), Esc schließt, und danach kehrt der Fokus
// zum auslösenden Element zurück. `beforeClose` kann das Schließen verhindern,
// z. B. damit ein angefangener Entwurf nicht versehentlich verloren geht.
// Ohne `beforeClose` schützt der Dialog selbst: Wurde etwas eingegeben, fragen Esc, „Schließen“
// und der Klick daneben vor dem Verwerfen (UX-Audit 16.11. VW-26; Regel in docs/ui-rueckmeldungen.md).
import { useEffect, useId, useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { t } from '../i18n/index.ts'
import { confirmDiscard } from './leaveGuard.ts'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({
  title,
  onClose,
  beforeClose,
  guard = true,
  children,
}: {
  title: string
  onClose: () => void
  /** Liefert false, wenn der Dialog offen bleiben soll. */
  beforeClose?: () => boolean | Promise<boolean>
  /** false: Eingaben sind nichts, was verloren gehen kann (z. B. ein Suchfeld). */
  guard?: boolean
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const latest = useRef({ onClose, beforeClose, guard })
  useEffect(() => {
    latest.current = { onClose, beforeClose, guard }
  })
  // Seit dem Öffnen wurde ein Feld geändert
  const touched = useRef(false)
  const asking = useRef(false)

  // Beim Öffnen: Fokus in den Dialog, Hintergrund sperren; beim Schließen zurück.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const host = ref.current?.closest('.modal-host')
    const others = Array.from(document.body.children).filter(
      (el) => el !== host && !el.hasAttribute('inert') && el.tagName !== 'SCRIPT',
    )
    for (const el of others) el.setAttribute('inert', '')
    ref.current?.focus()
    return () => {
      for (const el of others) el.removeAttribute('inert')
      if (previous && document.contains(previous)) previous.focus()
    }
  }, [])

  async function requestClose() {
    const before = latest.current.beforeClose
    if (before) {
      if (!(await before())) return
    } else if (latest.current.guard && touched.current) {
      if (asking.current) return
      asking.current = true
      try {
        if (!(await confirmDiscard(true))) return
      } finally {
        asking.current = false
      }
    }
    latest.current.onClose()
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      void requestClose()
      return
    }
    if (e.key !== 'Tab' || !ref.current) return
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (items.length === 0) {
      e.preventDefault()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === ref.current)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return createPortal(
    <div className="modal-host">
      <div className="modal-backdrop" onMouseDown={() => void requestClose()}>
        <div
          className="modal card"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          ref={ref}
          onKeyDown={onKeyDown}
          onMouseDown={(e) => e.stopPropagation()}
          onInput={() => {
            touched.current = true
          }}
          onChange={() => {
            touched.current = true
          }}
        >
          <div className="modal-head">
            <h2 id={titleId}>{title}</h2>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void requestClose()}
            >
              {t('Schließen')}
            </button>
          </div>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  )
}
