// Bearbeiten direkt am Eintrag (Ralf 23.11.): Klickt man mitten in einer Liste auf „Bearbeiten“,
// erscheint das Formular unter genau diesem Eintrag statt oben auf der Seite außerhalb des
// Sichtbereichs. Die Liste setzt je Eintrag einen Platz (`EditSlot`), das Formular steht wie
// bisher an einer Stelle der Seite in `EditAt` und wird per Portal in den Platz des bearbeiteten
// Eintrags gehängt. Fehlt der Platz (neuer Eintrag, Eintrag ausgefiltert), bleibt das Formular an
// seiner Stelle. In beiden Fällen rollt die Seite zum Formular und das erste Feld bekommt den Fokus.
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

const wanted = new Map<string, number>()
const places = new Map<string, HTMLElement>()
const listeners = new Set<() => void>()

function emit() {
  for (const listener of [...listeners]) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Schlüssel eines Platzes, z. B. `editKey('uniform', 12)` → „uniform:12“ */
export function editKey(list: string, id: string | number | null | undefined): string | null {
  return id === null || id === undefined || id === '' ? null : `${list}:${id}`
}

/**
 * Platz für das Formular unter einem Listeneintrag. Bleibt leer (rendert nichts), solange der
 * Eintrag nicht bearbeitet wird. In Tabellen mit `colSpan` als eigene Zeile nach dem Eintrag.
 */
export function EditSlot({ id, colSpan }: { id: string | null; colSpan?: number }) {
  const active = useSyncExternalStore(
    subscribe,
    () => !!id && wanted.has(id),
    () => false,
  )
  const register = useCallback(
    (el: HTMLElement | null) => {
      if (!id) return
      if (el) places.set(id, el)
      else if (places.get(id)) places.delete(id)
      emit()
    },
    [id],
  )
  if (!active) return null
  if (colSpan)
    return (
      <tr className="edit-slot-row">
        <td colSpan={colSpan} className="edit-slot" ref={register} />
      </tr>
    )
  return <div className="edit-slot" ref={register} />
}

const FIELDS =
  'input:not([type=hidden]):not([disabled]):not([readonly]), select:not([disabled]), textarea:not([disabled]):not([readonly]), [contenteditable=true]'

/** Zum Formular rollen und das erste Feld fokussieren, wenn der Fokus noch nicht darin steht. */
export function bringIntoView(box: HTMLElement | null) {
  if (!box) return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const rect = box.getBoundingClientRect()
  const high = window.innerHeight || document.documentElement.clientHeight
  // Lange Formulare mit dem Anfang nach oben, kurze nur so weit wie nötig
  if (high && (rect.top < 0 || rect.bottom > high))
    box.scrollIntoView?.({
      block: rect.height > high * 0.8 ? 'start' : 'nearest',
      behavior: reduce ? 'auto' : 'smooth',
    })
  if (box.contains(document.activeElement)) return
  box.querySelector<HTMLElement>(FIELDS)?.focus({ preventScroll: true })
}

/**
 * Formular, das am Eintrag `at` erscheint (siehe `EditSlot`), sonst an dieser Stelle.
 * `at` = null: neuer Eintrag, das Formular bleibt hier.
 */
export function EditAt({
  at,
  quiet = false,
  children,
}: {
  at: string | null
  /** Formular steht ohnehin immer da: nur beim Bearbeiten eines Eintrags hinrollen */
  quiet?: boolean
  children: ReactNode
}) {
  useLayoutEffect(() => {
    if (!at) return
    wanted.set(at, (wanted.get(at) ?? 0) + 1)
    emit()
    return () => {
      const n = (wanted.get(at) ?? 1) - 1
      if (n > 0) wanted.set(at, n)
      else wanted.delete(at)
      emit()
    }
  }, [at])
  const target = useSyncExternalStore(
    subscribe,
    () => (at ? (places.get(at) ?? null) : null),
    () => null,
  )
  // Kein Platz gefunden (z. B. Eintrag ausgefiltert): nach einem Bild hier zeigen
  const [missing, setMissing] = useState<string | null>(null)
  useEffect(() => {
    if (!at || target) return
    const check = () => {
      if (!places.get(at)) setMissing(at)
    }
    if (typeof requestAnimationFrame === 'undefined') {
      check()
      return
    }
    const frame = requestAnimationFrame(check)
    return () => cancelAnimationFrame(frame)
  }, [at, target])
  const box = useRef<HTMLDivElement>(null)
  const where = target ? 'slot' : !at || missing === at ? 'here' : 'waiting'
  useEffect(() => {
    if (where !== 'waiting' && (at || !quiet)) bringIntoView(box.current)
  }, [where, at, quiet])
  if (where === 'waiting') return null
  const content = (
    <div className="edit-at" ref={box}>
      {children}
    </div>
  )
  return target ? createPortal(content, target) : content
}
