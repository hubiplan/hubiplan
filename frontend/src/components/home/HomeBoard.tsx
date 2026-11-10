// Startseite selbst zusammenstellen (S-04): Unter „Startseite anpassen“ zieht jede Person die
// Blöcke direkt auf der Startseite an ihren Platz (überall am Block anfassen, oder Griff und
// Pfeiltasten), blendet sie aus und stellt sie auf ganze oder halbe Breite. Die Anordnung gilt
// je Arbeitsbereich; ohne eigene gilt der Standard (homeLayout.ts).
import { useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent, ReactNode } from 'react'
import { homeActionsApi } from '../../api/homeActions.ts'
import type { HomeActionsData, HomeActionsUpdate } from '../../api/homeActions.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { GripIcon } from '../Sortable.tsx'
import { BLOCK, layoutOf, placeBlocks } from './homeLayout.ts'
import type { PlacedBlock, HomeBlock } from './homeLayout.ts'
import { t } from '../../i18n/index.ts'

/** Einstellungen der Startseite am Konto, einmal für alle Blöcke geladen */
export interface HomePrefs {
  data: HomeActionsData | null
  busy: boolean
  save: (body: HomeActionsUpdate) => Promise<void>
}

function moveKey(order: string[], key: string, to: number): string[] {
  const rest = order.filter((k) => k !== key)
  rest.splice(Math.max(0, Math.min(to, rest.length)), 0, key)
  return rest
}

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i])

export function HomeBoard({
  scope,
  name,
  blocks,
  children,
}: {
  /** Arbeitsbereich, z. B. „o12“ */
  scope: string
  /** Name der Einheit für den Hinweis beim Anpassen */
  name: string
  blocks: (prefs: HomePrefs) => HomeBlock[]
  /** Steht immer am Ende (z. B. Hinweis ohne Module) */
  children?: ReactNode
}) {
  const { data, error: loadError, setData } = useLoad(() => homeActionsApi.get(), [])
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [announce, setAnnounce] = useState('')
  // Reihenfolge während des Ziehens und bis der Server sie bestätigt
  const [draft, setDraft] = useState<string[] | null>(null)
  const [dragKey, setDragKey] = useState<string | null>(null)
  const boxes = useRef(new Map<string, HTMLElement>())
  const handles = useRef(new Map<string, HTMLButtonElement>())
  const drag = useRef<{ key: string; order: string[]; start: string[]; over: string | null }>(null)
  const focusAfter = useRef<string | null>(null)

  useLayoutEffect(() => {
    if (focusAfter.current !== null) {
      handles.current.get(focusAfter.current)?.focus()
      focusAfter.current = null
    }
  })

  async function save(body: HomeActionsUpdate) {
    setBusy(true)
    setError(null)
    try {
      setData(await homeActionsApi.update(body))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
      setDraft(null)
    }
  }

  // Erst nach dem Laden zeigen, damit die eigene Anordnung nicht nachträglich umspringt
  if (!data && !loadError) return null
  const prefs: HomePrefs = { data, busy, save }
  const available = blocks(prefs)
  const own = data?.layout?.[scope]
  const saved = placeBlocks(available, own)
  const byKey = new Map(saved.map((b) => [b.key, b]))
  const placed = draft
    ? draft.map((k) => byKey.get(k)).filter((b): b is PlacedBlock => b !== undefined)
    : saved
  const order = placed.map((b) => b.key)
  // Schnellaktionen lassen sich auch für alle Bereiche ausblenden (Mein Konto › Profil)
  const actionsOff = (data?.hidden ?? []).includes('*')
  const visible = (b: PlacedBlock) => b.shown && !(b.key === BLOCK.actions && actionsOff)

  const store = (next: PlacedBlock[], extra: HomeActionsUpdate = {}) =>
    save({ ...extra, layout: { [scope]: layoutOf(next) } })
  const change = (key: string, part: Partial<PlacedBlock>) => {
    const next = placed.map((b) => (b.key === key ? { ...b, ...part } : b))
    // Schnellaktionen wieder zeigen hebt auch das Ausblenden für alle Bereiche auf
    const extra =
      key === BLOCK.actions && part.shown && actionsOff
        ? { hidden: (data?.hidden ?? []).filter((k) => k !== '*') }
        : {}
    void store(next, extra)
  }
  const commit = (next: string[], key: string) => {
    setDraft(next)
    const label = byKey.get(key)?.label ?? ''
    setAnnounce(
      t('{x} steht jetzt an Stelle {x2} von {n}.', {
        x: label,
        x2: next.indexOf(key) + 1,
        n: next.length,
      }),
    )
    void store(next.map((k) => byKey.get(k) as PlacedBlock))
  }

  function onPointerDown(e: PointerEvent<HTMLElement>, key: string) {
    if (!editing || busy || e.button !== 0) return
    // Bedienelemente im Block behalten ihren Klick
    if (
      (e.target as HTMLElement).closest(
        'input, label, select, textarea, a, button:not(.drag-handle)',
      )
    )
      return
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { key, order, start: order, over: null }
    setDragKey(key)
  }

  function onPointerMove(e: PointerEvent<HTMLElement>) {
    const d = drag.current
    if (!d) return
    // Der Block unter dem Zeiger gibt seinen Platz her; erst nach dem Verlassen wieder
    let over: string | null = null
    for (const k of d.order) {
      if (k === d.key) continue
      const box = boxes.current.get(k)?.getBoundingClientRect()
      if (
        box &&
        e.clientX >= box.left &&
        e.clientX <= box.right &&
        e.clientY >= box.top &&
        e.clientY <= box.bottom
      )
        over = k
    }
    if (over === d.over) return
    d.over = over
    if (over === null) return
    const next = moveKey(d.order, d.key, d.order.indexOf(over))
    if (!same(next, d.order)) {
      d.order = next
      setDraft(next)
    }
  }

  function onPointerUp() {
    const d = drag.current
    drag.current = null
    setDragKey(null)
    if (d && !same(d.order, d.start)) commit(d.order, d.key)
    else setDraft(null)
  }

  function onPointerCancel() {
    drag.current = null
    setDragKey(null)
    setDraft(null)
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, key: string) {
    const at = order.indexOf(key)
    const to =
      e.key === 'ArrowUp' || e.key === 'ArrowLeft'
        ? at - 1
        : e.key === 'ArrowDown' || e.key === 'ArrowRight'
          ? at + 1
          : e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? order.length - 1
              : null
    if (to === null) return
    e.preventDefault()
    if (busy || to < 0 || to >= order.length || to === at) return
    focusAfter.current = key
    commit(moveKey(order, key, to), key)
  }

  const shown = editing ? placed : placed.filter(visible)
  return (
    <>
      {available.length > 0 && (
        <div className="home-board-head">
          {editing && (
            <p className="muted small">
              {t(
                'Ziehe die Blöcke an ihren Platz (am Handy an der Leiste mit dem Namen), oder nimm den Griff und die Pfeiltasten. Die Anordnung gilt für {name}.',
                { name },
              )}
            </p>
          )}
          <div className="button-row push-right">
            {editing && own && (
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => void save({ layout: { [scope]: null } })}
              >
                {t('Standard wiederherstellen')}
              </button>
            )}
            <button
              type="button"
              className={editing ? 'button button-primary' : 'button'}
              aria-pressed={editing}
              onClick={() => setEditing(!editing)}
            >
              {editing ? t('Fertig') : t('Startseite anpassen')}
            </button>
          </div>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      <div className={editing ? 'tiles home-grid home-grid-editing' : 'tiles home-grid'}>
        {shown.map((b) => {
          const classes = [
            'home-block',
            b.wide && 'home-block-wide',
            editing && !visible(b) && 'home-block-off',
            dragKey === b.key && 'home-block-dragging',
          ]
            .filter(Boolean)
            .join(' ')
          return (
            <div
              key={b.key}
              className={classes}
              ref={(el) => {
                if (el) boxes.current.set(b.key, el)
                else boxes.current.delete(b.key)
              }}
              onPointerDown={(e) => onPointerDown(e, b.key)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerCancel}
            >
              {editing && (
                <div className="home-block-bar" role="group" aria-label={b.label}>
                  <button
                    type="button"
                    className="drag-handle"
                    ref={(el) => {
                      if (el) handles.current.set(b.key, el)
                      else handles.current.delete(b.key)
                    }}
                    aria-label={t('{x} verschieben', { x: b.label })}
                    aria-roledescription={t('Griff zum Verschieben')}
                    title={t('Ziehen zum Verschieben (oder Pfeiltasten)')}
                    onKeyDown={(e) => onKeyDown(e, b.key)}
                  >
                    <GripIcon />
                  </button>
                  <strong className="home-block-name">{b.label}</strong>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={visible(b)}
                      aria-label={t('{x} zeigen', { x: b.label })}
                      aria-busy={busy || undefined}
                      onChange={(e) => {
                        if (!busy) change(b.key, { shown: e.target.checked })
                      }}
                    />
                    <span>{t('Zeigen')}</span>
                  </label>
                  <label className="checkbox home-block-wide-option">
                    <input
                      type="checkbox"
                      checked={b.wide}
                      aria-label={t('{x} über die ganze Breite', { x: b.label })}
                      aria-busy={busy || undefined}
                      onChange={(e) => {
                        if (!busy) change(b.key, { wide: e.target.checked })
                      }}
                    />
                    <span>{t('Ganze Breite')}</span>
                  </label>
                </div>
              )}
              {/* Beim Anpassen nur Vorschau: Links und Knöpfe im Block reagieren nicht */}
              <div
                className="home-block-content"
                inert={editing || undefined}
                data-empty={t('Zurzeit ohne Inhalt')}
              >
                {b.render()}
              </div>
            </div>
          )
        })}
        {children}
      </div>
    </>
  )
}
