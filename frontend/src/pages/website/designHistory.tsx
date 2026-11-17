// Rückgängig und Wiederholen für die Gestaltung der Webseite (Konzept feinabstimmung-uebersichtlich,
// F6, Ralf 16.11.2026): Design und Farben, Feinabstimmung und Darstellung der Bereiche teilen sich
// einen Verlauf mit bis zu 50 Schritten. Er gilt, solange die Seite offen ist; Veröffentlichen
// oder Verwerfen beginnt ihn neu. Strg+Z / Strg+Umschalt+Z (oder Strg+Y) außerhalb von Textfeldern.
import { useCallback, useEffect, useRef, useState } from 'react'
import { t, tc } from '../../i18n/index.ts'

type Step = { key: string; prev: unknown; next: unknown }
const LIMIT = 50

export type DesignHistory = {
  /** Wert setzen und im Verlauf merken */
  track: (key: string, next: unknown) => void
  undo: () => void
  redo: () => void
  canUndo: boolean
  canRedo: boolean
  clear: () => void
}

export function useDesignHistory(
  current: (key: string) => unknown,
  apply: (key: string, value: unknown) => void,
): DesignHistory {
  const [past, setPast] = useState<Step[]>([])
  const [future, setFuture] = useState<Step[]>([])
  const track = useCallback(
    (key: string, next: unknown) => {
      const prev = current(key)
      if (JSON.stringify(prev) !== JSON.stringify(next)) {
        setPast((p) => [...p.slice(-(LIMIT - 1)), { key, prev, next }])
        setFuture([])
      }
      apply(key, next)
    },
    [current, apply],
  )
  const undo = useCallback(() => {
    const step = past.at(-1)
    if (!step) return
    setPast(past.slice(0, -1))
    setFuture((f) => [...f, step])
    apply(step.key, step.prev)
  }, [past, apply])
  const redo = useCallback(() => {
    const step = future.at(-1)
    if (!step) return
    setFuture(future.slice(0, -1))
    setPast((p) => [...p, step])
    apply(step.key, step.next)
  }, [future, apply])
  const clear = useCallback(() => {
    setPast([])
    setFuture([])
  }, [])
  return { track, undo, redo, canUndo: past.length > 0, canRedo: future.length > 0, clear }
}

function editable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  if (target instanceof HTMLTextAreaElement) return true
  if (target instanceof HTMLInputElement)
    return !['checkbox', 'radio', 'button', 'submit', 'range', 'color'].includes(target.type)
  return false
}

/** Knöpfe „Rückgängig“ und „Wiederholen“; solange sie zu sehen sind, gelten die Tasten */
export function UndoBar({ history }: { history: DesignHistory }) {
  const ref = useRef(history)
  useEffect(() => {
    ref.current = history
  })
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || editable(e.target)) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey && ref.current.canUndo) {
        e.preventDefault()
        ref.current.undo()
      } else if (((key === 'z' && e.shiftKey) || key === 'y') && ref.current.canRedo) {
        e.preventDefault()
        ref.current.redo()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  return (
    <div className="undo-bar" role="group" aria-label={t('Verlauf der Gestaltung')}>
      <button
        type="button"
        className="button button-ghost"
        disabled={!history.canUndo}
        title={t('Strg+Z')}
        onClick={history.undo}
      >
        ↶ {t('Rückgängig')}
      </button>
      <button
        type="button"
        className="button button-ghost"
        disabled={!history.canRedo}
        title={t('Strg+Umschalt+Z')}
        onClick={history.redo}
      >
        ↷ {tc('Gestaltung', 'Wiederholen')}
      </button>
    </div>
  )
}
