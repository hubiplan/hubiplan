// Eingeblendete Formulare („Neu …“ unter einer Liste) bekommen den Fokus und rücken ins Bild
// (WCAG 2.4.3, UX-Audit 16.11. VW-43). Dialoge machen das selbst.
import { useEffect, useRef } from 'react'

const FIELDS =
  'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])'

/**
 * Ref für das Formular; `active` nur für neu eingeblendete, nicht für geöffnete Datensätze.
 * `onEscape` schließt das Formular mit Escape wie ein Dialog; die Rückfrage bei ungespeicherten
 * Eingaben übernimmt der Aufrufer (confirmLeave).
 */
export function useRevealFocus<T extends HTMLElement>(active: boolean, onEscape?: () => void) {
  const ref = useRef<T>(null)
  const escape = useRef(onEscape)
  useEffect(() => {
    escape.current = onEscape
  })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || !escape.current) return
      // offene Auswahllisten und Menüs schließen zuerst sich selbst
      const target = e.target as HTMLElement | null
      if (target?.closest('[aria-expanded="true"], [role="listbox"], [role="menu"]')) return
      e.preventDefault()
      escape.current()
    }
    el.addEventListener('keydown', onKey)
    return () => el.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => {
    const el = ref.current
    if (!active || !el) return
    if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest' })
    el.querySelector<HTMLElement>(FIELDS)?.focus()
    // nur beim Einblenden, nicht bei jeder Änderung
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return ref
}
