// Eine dauerhaft vorhandene Ansage-Region für die ganze App (WCAG 4.1.3, UX-Audit 16.11.
// VW-29, X-04). Screenreader sagen Text nur verlässlich an, wenn die Region schon vor der
// Änderung im Dokument steht; ein Element, das erst mit seinem Text entsteht (z. B. die
// Ladezeile), wird oft übergangen. Die Regionen hängen an document.body, wie die Dialoge.
import { useEffect } from 'react'

function region(id: string, urgent: boolean): HTMLElement | null {
  if (typeof document === 'undefined') return null
  let el = document.getElementById(id)
  if (!el) {
    el = document.createElement('div')
    el.id = id
    el.className = 'sr-only'
    // ohne role: aria-live genügt, und sichtbare Meldungen bleiben die einzigen mit Rolle
    el.setAttribute('aria-live', urgent ? 'assertive' : 'polite')
    el.setAttribute('aria-atomic', 'true')
    document.body.appendChild(el)
  }
  return el
}

/** Regionen anlegen, bevor die erste Meldung kommt (einmal beim Start der App). */
export function prepareAnnouncements() {
  region('ansage-hoeflich', false)
  region('ansage-dringend', true)
}

/** Text ansagen lassen; `urgent` unterbricht (Fehler), sonst höflich (Status). */
export function announce(text: string, urgent = false) {
  const el = region(urgent ? 'ansage-dringend' : 'ansage-hoeflich', urgent)
  if (!el) return
  // Leeren und neu setzen: derselbe Text wird sonst kein zweites Mal angesagt
  el.textContent = ''
  window.setTimeout(() => {
    el.textContent = text
  }, 50)
}

/**
 * Sagt `text` an, solange die Komponente steht; erst nach `delay` Millisekunden, damit kurzes
 * Laden nicht dauernd angesagt wird.
 */
export function useAnnounce(text: string, delay = 400) {
  useEffect(() => {
    const timer = window.setTimeout(() => announce(text), delay)
    return () => window.clearTimeout(timer)
  }, [text, delay])
}
