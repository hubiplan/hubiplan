// Startseite selbst zusammenstellen (S-04): Unter „Startseite anpassen“ zieht jede Person die
// Blöcke direkt auf der Startseite an ihren Platz (überall am Block anfassen, oder Griff und
// Pfeiltasten), blendet sie aus und ändert an der Ecke Breite und Höhe. Das Raster hat zwölf
// Spalten und feine Zeilen, so rutschen Blöcke in Lücken nach. Die Anordnung gilt je
// Arbeitsbereich; ohne eigene gilt der Standard (homeLayout.ts).
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, PointerEvent, ReactNode } from 'react'
import { homeActionsApi } from '../../api/homeActions.ts'
import type { HomeActionsData, HomeActionsUpdate } from '../../api/homeActions.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { GripIcon } from '../Sortable.tsx'
import {
  BLOCK,
  GRID_COLUMNS,
  ROW_REM,
  clampCols,
  clampRows,
  layoutOf,
  placeBlocks,
  widthLabel,
} from './homeLayout.ts'
import type { PlacedBlock, HomeBlock } from './homeLayout.ts'
import { t, tc } from '../../i18n/index.ts'

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

/** Abstand unter jedem Block in Rasterzeilen (2 × 0,5 rem = 1 rem) */
const GAP_ROWS = 2
/** Schritt der Pfeiltasten an der Ecke: 2 rem */
const KEY_ROWS = 4
/** Breiten zur Auswahl: ¼, ⅓, ½, ⅔, ¾, ganz */
const WIDTHS = [3, 4, 6, 8, 9, 12]

function rowPx(): number {
  const size = parseFloat(getComputedStyle(document.documentElement).fontSize)
  return (size || 16) * ROW_REM
}

interface SizeDraft {
  key: string
  cols: number
  rows: number | null
}

interface ResizeStart {
  key: string
  x: number
  y: number
  cols: number
  rows: number
  colW: number
  row: number
}

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
  // Größe während des Ziehens an der Ecke und bis der Server sie bestätigt
  const [sizeDraft, setSizeDraft] = useState<SizeDraft | null>(null)
  // Gemessene Höhe (in Rasterzeilen) jedes Blocks samt Leiste; daraus folgt sein Platz im Raster
  const [spans, setSpans] = useState<Record<string, number>>({})
  const grid = useRef<HTMLDivElement | null>(null)
  const boxes = useRef(new Map<string, HTMLElement>())
  const inners = useRef(new Map<string, HTMLElement>())
  const contents = useRef(new Map<string, HTMLElement>())
  const handles = useRef(new Map<string, HTMLButtonElement>())
  const resizeHandles = useRef(new Map<string, HTMLButtonElement>())
  const observer = useRef<ResizeObserver | null>(null)
  const drag = useRef<{ key: string; order: string[]; start: string[]; over: string | null }>(null)
  const resize = useRef<ResizeStart | null>(null)
  const focusAfter = useRef<{ key: string; resize: boolean } | null>(null)

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      const row = rowPx()
      setSpans((prev) => {
        let next = prev
        for (const entry of entries) {
          const el = entry.target as HTMLElement
          const key = el.dataset.block
          const span = Math.max(1, Math.ceil(el.getBoundingClientRect().height / row - 0.01))
          if (key && next[key] !== span) {
            if (next === prev) next = { ...prev }
            next[key] = span
          }
        }
        return next
      })
    })
    observer.current = ro
    inners.current.forEach((el) => ro.observe(el))
    return () => {
      ro.disconnect()
      observer.current = null
    }
  }, [])

  // Pfeiltasten: Fokus bleibt auf dem Griff bzw. der Ecke des Blocks
  useLayoutEffect(() => {
    const f = focusAfter.current
    if (f !== null) {
      ;(f.resize ? resizeHandles : handles).current.get(f.key)?.focus()
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
      setSizeDraft(null)
    }
  }

  // Erst nach dem Laden zeigen, damit die eigene Anordnung nicht nachträglich umspringt
  if (!data && !loadError) return null
  const prefs: HomePrefs = { data, busy, save }
  const available = blocks(prefs)
  const own = data?.layout?.[scope]
  const saved = placeBlocks(available, own)
  const byKey = new Map(saved.map((b) => [b.key, b]))
  const placed = (
    draft ? draft.map((k) => byKey.get(k)).filter((b): b is PlacedBlock => b !== undefined) : saved
  ).map((b) =>
    sizeDraft?.key === b.key ? { ...b, cols: sizeDraft.cols, rows: sizeDraft.rows } : b,
  )
  const order = placed.map((b) => b.key)
  // Schnellaktionen lassen sich auch für alle Bereiche ausblenden (Mein Konto › Profil)
  const actionsOff = (data?.hidden ?? []).includes('*')
  const visible = (b: PlacedBlock) => b.shown && !(b.key === BLOCK.actions && actionsOff)
  // Höhe des Inhalts in Rasterzeilen: eingestellt oder gemessen (ohne Leiste beim Anpassen)
  const rowsOf = (b: PlacedBlock) => {
    if (b.rows !== null) return b.rows
    const h = contents.current.get(b.key)?.getBoundingClientRect().height ?? 0
    return h > 0 ? Math.ceil(h / rowPx()) : 20
  }

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
  const resizeTo = (b: PlacedBlock, cols: number, rows: number | null) => {
    setSizeDraft({ key: b.key, cols, rows })
    change(b.key, { cols, rows })
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
    void store(next.map((k) => placed.find((b) => b.key === k) as PlacedBlock))
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
    focusAfter.current = { key, resize: false }
    commit(moveKey(order, key, to), key)
  }

  // Ecke unten rechts: ziehen ändert Breite (in Spalten) und Höhe (in Rasterzeilen)
  function onResizeDown(e: PointerEvent<HTMLButtonElement>, b: PlacedBlock) {
    if (busy || e.button !== 0 || !grid.current) return
    e.preventDefault()
    e.stopPropagation()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const box = grid.current.getBoundingClientRect()
    const gap = parseFloat(getComputedStyle(grid.current).columnGap) || 0
    resize.current = {
      key: b.key,
      x: e.clientX,
      y: e.clientY,
      cols: b.cols,
      rows: rowsOf(b),
      colW: (box.width + gap) / GRID_COLUMNS || 1,
      row: rowPx(),
    }
  }

  function onResizeMove(e: PointerEvent<HTMLButtonElement>) {
    const r = resize.current
    if (!r) return
    e.stopPropagation()
    const cols = clampCols(r.cols + (e.clientX - r.x) / r.colW)
    const rows = clampRows(r.rows + (e.clientY - r.y) / r.row)
    if (sizeDraft?.key !== r.key || sizeDraft.cols !== cols || sizeDraft.rows !== rows)
      setSizeDraft({ key: r.key, cols, rows })
  }

  function onResizeUp(e: PointerEvent<HTMLButtonElement>, b: PlacedBlock) {
    const r = resize.current
    resize.current = null
    if (!r) return
    e.stopPropagation()
    if (sizeDraft?.key === b.key && (sizeDraft.cols !== r.cols || sizeDraft.rows !== r.rows))
      resizeTo(b, sizeDraft.cols, sizeDraft.rows)
    else setSizeDraft(null)
  }

  function onResizeKey(e: KeyboardEvent<HTMLButtonElement>, b: PlacedBlock) {
    const step: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -KEY_ROWS],
      ArrowDown: [0, KEY_ROWS],
    }
    const d = step[e.key]
    if (!d) return
    e.preventDefault()
    if (busy) return
    focusAfter.current = { key: b.key, resize: true }
    resizeTo(b, clampCols(b.cols + d[0]), d[1] === 0 ? b.rows : clampRows(rowsOf(b) + d[1]))
  }

  const shown = editing ? placed : placed.filter(visible)
  return (
    <>
      {available.length > 0 && (
        <div className="home-board-head">
          {editing && (
            <p className="muted small">
              {t(
                'Ziehe die Blöcke an ihren Platz (am Handy an der Leiste mit dem Namen), oder nimm den Griff und die Pfeiltasten. Die Ecke unten rechts ändert Breite und Höhe. Die Anordnung gilt für {name}.',
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
      <div ref={grid} className={editing ? 'tiles home-grid home-grid-editing' : 'tiles home-grid'}>
        {shown.map((b) => {
          const style = {
            '--home-cols': b.cols,
            '--home-span': (spans[b.key] ?? b.rows ?? 1) + GAP_ROWS,
            ...(b.rows !== null ? { '--home-rows': b.rows } : {}),
          } as CSSProperties
          const widths = WIDTHS.includes(b.cols)
            ? WIDTHS
            : [...WIDTHS, b.cols].sort((x, y) => x - y)
          const classes = [
            'home-block',
            b.rows !== null && 'home-block-fixed',
            editing && !visible(b) && 'home-block-off',
            dragKey === b.key && 'home-block-dragging',
          ]
            .filter(Boolean)
            .join(' ')
          return (
            <div
              key={b.key}
              className={classes}
              style={style}
              data-cols={b.cols}
              ref={(el) => {
                if (el) boxes.current.set(b.key, el)
                else boxes.current.delete(b.key)
              }}
              onPointerDown={(e) => onPointerDown(e, b.key)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerCancel}
            >
              <div
                className="home-block-inner"
                data-block={b.key}
                ref={(el) => {
                  const before = inners.current.get(b.key)
                  if (before && before !== el) observer.current?.unobserve(before)
                  if (el) {
                    inners.current.set(b.key, el)
                    observer.current?.observe(el)
                  } else inners.current.delete(b.key)
                }}
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
                    <label className="home-block-width">
                      <span>{tc('size', 'Breite')}</span>
                      <select
                        value={b.cols}
                        aria-label={t('{x}: Breite', { x: b.label })}
                        aria-busy={busy || undefined}
                        onChange={(e) => {
                          if (!busy) resizeTo(b, Number(e.target.value), b.rows)
                        }}
                      >
                        {widths.map((w) => (
                          <option key={w} value={w}>
                            {w === GRID_COLUMNS ? tc('size', 'ganz') : widthLabel(w)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="checkbox home-block-height">
                      <input
                        type="checkbox"
                        checked={b.rows === null}
                        aria-label={t('{x}: Höhe nach Inhalt', { x: b.label })}
                        aria-busy={busy || undefined}
                        onChange={(e) => {
                          if (!busy)
                            resizeTo(b, b.cols, e.target.checked ? null : clampRows(rowsOf(b)))
                        }}
                      />
                      <span>{t('Höhe nach Inhalt')}</span>
                    </label>
                  </div>
                )}
                {/* Beim Anpassen nur Vorschau: Links und Knöpfe im Block reagieren nicht */}
                <div
                  className="home-block-content"
                  ref={(el) => {
                    if (el) contents.current.set(b.key, el)
                    else contents.current.delete(b.key)
                  }}
                  inert={editing || undefined}
                  data-empty={t('Zurzeit ohne Inhalt')}
                >
                  {b.render()}
                </div>
                {editing && (
                  <button
                    type="button"
                    className="home-block-resize"
                    ref={(el) => {
                      if (el) resizeHandles.current.set(b.key, el)
                      else resizeHandles.current.delete(b.key)
                    }}
                    aria-label={t('{x}: Größe ändern', { x: b.label })}
                    title={t('Ziehen ändert Breite und Höhe (oder Pfeiltasten)')}
                    onPointerDown={(e) => onResizeDown(e, b)}
                    onPointerMove={onResizeMove}
                    onPointerUp={(e) => onResizeUp(e, b)}
                    onPointerCancel={() => {
                      resize.current = null
                      setSizeDraft(null)
                    }}
                    onKeyDown={(e) => onResizeKey(e, b)}
                  >
                    <svg
                      viewBox="0 0 12 12"
                      width="12"
                      height="12"
                      aria-hidden="true"
                      focusable="false"
                    >
                      <path
                        d="M11 3v8H3M11 7v4H7"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                      />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {/* Weitere Karten (z. B. „Übersicht“) stehen unter dem Raster: im feinen Raster hätten sie
          nur eine Zeile (0,5 rem) und lägen über der Fußzeile */}
      {children && <div className="home-board-extra">{children}</div>}
    </>
  )
}
