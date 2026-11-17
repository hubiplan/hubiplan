// Eingeblendete Formulare („Neu …“ unter einer Liste) bekommen den Fokus und rücken ins Bild
// (WCAG 2.4.3, UX-Audit 16.11. VW-43). Dialoge machen das selbst.
import { useEffect, useRef } from 'react'

const FIELDS =
  'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])'

/** Ref für das Formular; `active` nur für neu eingeblendete, nicht für geöffnete Datensätze. */
export function useRevealFocus<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T>(null)
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
