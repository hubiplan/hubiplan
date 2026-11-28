import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import { meetingApi } from '../../api/meetings.ts'
import type { AgendaItem, AgendaType, Meeting } from '../../api/meetings.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useAutoSave } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { Term } from '../../learning/Aids.tsx'
import { SaveStatus } from '../../components/ui.tsx'
import './meetings.css'
import { GripIcon } from '../../components/Sortable.tsx'
import {
  addSub,
  agendaNumbers,
  attach,
  blockEnd,
  canMove,
  moveRow,
  normalize,
  parentIndex,
  removeRow,
  dropBlock,
} from './agendaTree.ts'
import type { AgendaRow, DropTarget } from './agendaTree.ts'
import { type Sync } from './meetingsHelpers.ts'

function typeLabel(type: AgendaType) {
  return {
    report: t('Bericht'),
    resolution: t('Beschluss'),
    election: t('Wahl'),
    other: t('Sonstiges'),
  }[type]
}

const AGENDA_TYPES: AgendaType[] = ['report', 'resolution', 'election', 'other']

function agendaRows(agenda: AgendaItem[]): AgendaRow[] {
  return normalize(
    agenda.map((a) => ({
      key: `id-${a.id}`,
      id: a.id,
      title: a.title,
      description: a.description,
      type: a.type,
      level: a.level ? 1 : 0,
    })),
  )
}

export function AgendaEditor({
  base,
  meeting,
  editable,
  sync,
}: {
  base: string
  meeting: Meeting
  editable: boolean
  sync: Sync
}) {
  const [items, setItems] = useState(() => agendaRows(meeting.agenda ?? []))
  const [, setErrors] = useState<Record<string, string>>({})
  const [announce, setAnnounce] = useState('')
  const [dragKey, setDragKey] = useState<string | null>(null)
  const newKey = useRef(0)
  const rowEls = useRef(new Map<string, HTMLElement>())
  const handles = useRef(new Map<string, HTMLButtonElement>())
  const focusAfter = useRef<string | null>(null)
  const drag = useRef<{ key: string; target: DropTarget | null } | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const plain = (rows: AgendaRow[]) => rows.map(({ key: _key, ...rest }) => rest)
  // Gespeichert wird die Tagesordnung als Ganzes, sobald jeder Punkt einen Titel hat
  const complete = items.every((item) => item.title.trim() !== '')
  const values = useMemo(() => ({ items }), [items])
  const auto = useAutoSave(
    { values, setErrors },
    async (_changes, current) => {
      const sent = current.items
      const result = await meetingApi.saveAgenda(base, sync.current(), plain(sent))
      sync.stored(result)
      // Neue Punkte bekommen ihre Nummer vom Server, sonst entstünden sie beim nächsten
      // Speichern noch einmal
      const ids = new Map(sent.map((row, i) => [row.key, result.agenda?.[i]?.id]))
      setItems((rows) => {
        let changed = false
        const next = rows.map((row) => {
          const id = ids.get(row.key)
          if (!id || row.id) return row
          changed = true
          return { ...row, id }
        })
        return changed ? next : rows
      })
    },
    { enabled: editable && complete },
  )
  useDraftGuard(editable && !complete, () => setItems(agendaRows(sync.current().agenda ?? [])))
  const numbers = agendaNumbers(items.map((item) => item.level))
  const change = (index: number, patch: Partial<AgendaRow>) =>
    setItems(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  const nextKey = () => `neu-${(newKey.current += 1)}`

  // Pfeiltasten am Griff: Fokus bleibt auf dem verschobenen Punkt
  useLayoutEffect(() => {
    if (focusAfter.current !== null) {
      handles.current.get(focusAfter.current)?.focus()
      focusAfter.current = null
    }
  })

  const told = (rows: AgendaRow[], key: string) => {
    const at = rows.findIndex((r) => r.key === key)
    const n = agendaNumbers(rows.map((r) => r.level))[at]
    const title = rows[at]?.title || t('Neuer Punkt')
    setAnnounce(t('{x} ist jetzt TOP {n}.', { x: title, n }))
  }

  function startDrag(e: PointerEvent<HTMLElement>, key: string, fromHandle: boolean) {
    if (e.button !== 0) return
    if (!fromHandle) {
      // Auf dem Handy nur am Griff, sonst ließe sich die Seite nicht mehr wischen
      if (e.pointerType === 'touch') return
      const target = e.target as HTMLElement
      if (target.closest('input, select, textarea, a, label, button')) return
    }
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { key, target: null }
    setDragKey(key)
  }

  function moveDrag(e: PointerEvent<HTMLElement>) {
    const d = drag.current
    if (!d) return
    const from = items.findIndex((r) => r.key === d.key)
    if (from < 0) return
    const inBlock = new Set(items.slice(from, blockEnd(items, from)).map((r) => r.key))
    // Mitte eines Punkts = darauf ablegen (Unterpunkt), oberes/unteres Viertel = davor/dahinter
    let target: DropTarget = { kind: 'before', key: null }
    const others = items.filter((r) => !inBlock.has(r.key))
    for (let j = 0; j < others.length; j += 1) {
      const box = rowEls.current.get(others[j].key)?.getBoundingClientRect()
      if (!box || e.clientY > box.bottom) continue
      const rel = (e.clientY - box.top) / box.height
      if (rel < 0.25) target = { kind: 'before', key: others[j].key }
      else if (rel <= 0.75) target = { kind: 'onto', key: others[j].key }
      else target = { kind: 'before', key: others[j + 1]?.key ?? null }
      break
    }
    if (JSON.stringify(target) !== JSON.stringify(d.target)) {
      d.target = target
      setDropTarget(target)
    }
  }

  function endDrag() {
    const d = drag.current
    drag.current = null
    setDragKey(null)
    setDropTarget(null)
    if (d?.target) {
      const next = dropBlock(items, d.key, d.target)
      if (next !== items) {
        setItems(next)
        told(next, d.key)
      }
    }
  }

  function cancelDrag() {
    drag.current = null
    setDragKey(null)
    setDropTarget(null)
  }

  function apply(next: AgendaRow[], key: string) {
    if (next === items) return
    focusAfter.current = key
    setItems(next)
    told(next, key)
  }

  function onHandleKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const key = items[index].key
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault()
      apply(moveRow(items, index, e.key === 'ArrowUp' ? -1 : 1), key)
    } else if (e.key === 'ArrowRight' && !items[index].level) {
      e.preventDefault()
      let p = index - 1
      while (p >= 0 && items[p].level) p -= 1
      if (p >= 0) apply(attach(items, index, items[p].key), key)
    } else if (e.key === 'ArrowLeft' && items[index].level) {
      e.preventDefault()
      apply(attach(items, index, null), key)
    }
  }

  if (!editable) {
    return (
      <section className="card">
        <h2>
          <Term k="agenda">{t('Tagesordnung')}</Term>
        </h2>
        <ol className="agenda-list">
          {items.map((item, index) => (
            <li key={item.key} className={item.level ? 'agenda-sub' : undefined}>
              <strong>
                {t('TOP {n}', { n: numbers[index] })}: <span>{item.title}</span>
              </strong>
              {item.description && <p className="muted">{item.description}</p>}
            </li>
          ))}
        </ol>
      </section>
    )
  }
  return (
    <form className="card stack" onSubmit={(e) => e.preventDefault()}>
      <h2>
        <Term k="agenda">{t('Tagesordnung')}</Term>
      </h2>
      {complete ? (
        <SaveStatus auto={auto} />
      ) : (
        <div className="save-status save-status-pending">
          <p role="status" aria-live="polite">
            {t('Noch nicht gespeichert: Jeder Punkt braucht einen Titel.')}
          </p>
        </div>
      )}
      <p className="muted small">
        {t(
          'Punkte am Griff oder an einer freien Stelle ziehen: zwischen zwei Punkten ablegen, um die Reihenfolge zu ändern, oder auf einem Punkt ablegen, um ihn zu dessen Unterpunkt zu machen. Unterpunkte ziehen mit ihrem Punkt mit. Am Griff gehen auch die Pfeiltasten (→ Unterpunkt, ← eigener Punkt).',
        )}
      </p>
      <ol className="agenda-edit">
        {items.map((item, index) => {
          const n = numbers[index]
          const parents = items.filter((r, j) => !r.level && j !== index)
          const parent = item.level ? items[parentIndex(items, index)] : undefined
          return (
            <li
              key={item.key}
              ref={(el) => {
                if (el) rowEls.current.set(item.key, el)
                else rowEls.current.delete(item.key)
              }}
              className={[
                'agenda-row',
                item.level && 'agenda-sub',
                dragKey === item.key && 'sortable-dragging',
                dragKey &&
                  dropTarget?.key === item.key &&
                  (dropTarget.kind === 'onto' ? 'agenda-drop-onto' : 'agenda-drop-before'),
                dragKey &&
                  dropTarget?.kind === 'before' &&
                  dropTarget.key === null &&
                  index === items.length - 1 &&
                  'agenda-drop-after',
              ]
                .filter(Boolean)
                .join(' ')}
              onPointerDown={(e) => startDrag(e, item.key, false)}
              onPointerMove={moveDrag}
              onPointerUp={endDrag}
              onPointerCancel={cancelDrag}
            >
              <div className="agenda-fields">
                <label className="field">
                  <span>{t('TOP {n}', { n })}</span>
                  <input
                    value={item.title}
                    maxLength={300}
                    required
                    onChange={(e) => change(index, { title: e.target.value })}
                  />
                </label>
                <label className="field">
                  <span>{t('Art des Punkts')}</span>
                  <select
                    value={item.type}
                    onChange={(e) => change(index, { type: e.target.value as AgendaType })}
                  >
                    {AGENDA_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {typeLabel(type)}
                      </option>
                    ))}
                  </select>
                </label>
                {index > 0 && (
                  <label className="field">
                    <span>{t('Gehört zu')}</span>
                    <select
                      value={parent?.key ?? ''}
                      onChange={(e) =>
                        apply(attach(items, index, e.target.value || null), item.key)
                      }
                    >
                      <option value="">{t('Eigener Punkt (oberste Ebene)')}</option>
                      {parents.map((p) => (
                        <option key={p.key} value={p.key}>
                          {t('Unterpunkt von TOP {n}', { n: numbers[items.indexOf(p)] })}
                          {p.title ? `: ${p.title}` : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="field agenda-wide">
                  <span>{t('Erläuterung')}</span>
                  <textarea
                    value={item.description}
                    maxLength={5000}
                    rows={2}
                    onChange={(e) => change(index, { description: e.target.value })}
                  />
                </label>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="drag-handle"
                  ref={(el) => {
                    if (el) handles.current.set(item.key, el)
                    else handles.current.delete(item.key)
                  }}
                  aria-label={t('TOP {n} verschieben', { n })}
                  aria-roledescription={t('Griff zum Verschieben')}
                  title={t(
                    'Ziehen zum Verschieben (Pfeiltasten: ↑ ↓ verschieben, → Unterpunkt, ← eigener Punkt)',
                  )}
                  onPointerDown={(e) => {
                    e.stopPropagation()
                    startDrag(e, item.key, true)
                  }}
                  onKeyDown={(e) => onHandleKey(e, index)}
                >
                  <GripIcon />
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={!canMove(items, index, -1)}
                  aria-label={t('TOP {n} nach oben', { n })}
                  onClick={() => apply(moveRow(items, index, -1), item.key)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={!canMove(items, index, 1)}
                  aria-label={t('TOP {n} nach unten', { n })}
                  onClick={() => apply(moveRow(items, index, 1), item.key)}
                >
                  ↓
                </button>
                {!item.level && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setItems(addSub(items, index, nextKey()))}
                  >
                    {t('Unterpunkt hinzufügen')}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={async () => {
                    // Gespeicherte Punkte verschwinden sofort: vorher fragen
                    if (
                      item.id &&
                      !(await confirmDialog({
                        final: true,
                        title: t('Tagesordnungspunkt entfernen?'),
                        message: t(
                          '„{title}“ wird mit seiner Erläuterung gelöscht. Unterpunkte bleiben als eigene Punkte stehen.',
                          { title: item.title },
                        ),
                        confirmLabel: t('Entfernen'),
                      }))
                    )
                      return
                    setItems((rows) => {
                      const at = rows.findIndex((r) => r.key === item.key)
                      return at < 0 ? rows : removeRow(rows, at)
                    })
                  }}
                >
                  {t('Entfernen')}
                </button>
              </div>
            </li>
          )
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            setItems([
              ...items,
              { key: nextKey(), title: '', description: '', type: 'other', level: 0 },
            ])
          }
        >
          {t('Punkt hinzufügen')}
        </button>
      </div>
    </form>
  )
}
