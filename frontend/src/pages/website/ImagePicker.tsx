import { useState } from 'react'
import type { WebsiteImage } from '../../api/website.ts'
import { Modal } from '../../components/Modal.tsx'
import { RightsHint } from '../../components/RightsHint.tsx'
import { Alert, Field } from '../../components/ui.tsx'
import { sortImages, useImageUpload, usePasteImages } from './imageTools.ts'
import type { ImageOrder } from './imageTools.ts'
import { t } from '../../i18n/index.ts'
import { ACCEPT, PAGE_SIZE, matches, type Unit } from './imagesHelpers.ts'
import { OrderField } from './OrderField.tsx'
import { ImageTiles } from './ImageTiles.tsx'

/**
 * Bild(er) wählen. Auf Seiten einer Untereinheit stehen erst deren Bilder und die des
 * Vereins allgemein, „alle Bilder“ zeigt den Rest. Neue Bilder gehören gleich zur
 * Untereinheit und sind danach ausgewählt.
 */
export function ImagePicker({
  images,
  unit,
  title = t('Bild wählen'),
  multiple = false,
  initial = [],
  max,
  onUploaded,
  onPick,
  onCancel,
}: {
  images: WebsiteImage[]
  unit?: Unit | null
  title?: string
  multiple?: boolean
  initial?: number[]
  max?: number
  onUploaded: () => void
  onPick: (images: WebsiteImage[]) => void
  onCancel: () => void
}) {
  const [q, setQ] = useState('')
  const [scope, setScope] = useState<'unit' | 'suggested' | 'all'>('suggested')
  const [order, setOrder] = useState<ImageOrder>('newest')
  const [chosen, setChosen] = useState<number[]>(initial)
  const [extra, setExtra] = useState<WebsiteImage[]>([])
  const [shown, setShown] = useState(PAGE_SIZE)
  const uploader = useImageUpload()
  const all = [...extra.filter((e) => !images.some((i) => i.id === e.id)), ...images]
  const suggested = (i: WebsiteImage) => !i.department || (unit ? i.department === unit.id : false)
  const anyOther = all.some((i) => !suggested(i))
  // Gerade hochgeladene Bilder bleiben vorn, der Rest nach der gewählten Sortierung
  const fresh = new Set(extra.map((e) => e.id))
  const filtered = [
    ...all.filter((i) => fresh.has(i.id)),
    ...sortImages(
      all.filter((i) => !fresh.has(i.id)),
      order,
    ),
  ].filter(
    (i) =>
      (scope === 'all' || (scope === 'unit' ? !!unit && i.department === unit.id : suggested(i))) &&
      matches(i, q, 'all', 'all'),
  )
  const full = max !== undefined && chosen.length >= max

  function click(i: WebsiteImage) {
    if (!multiple) {
      onPick([i])
      return
    }
    setChosen((c) => (c.includes(i.id) ? c.filter((x) => x !== i.id) : full ? c : [...c, i.id]))
  }

  usePasteImages(
    !uploader.working && !(multiple && full),
    (files) => void add(multiple ? files : files.slice(0, 1)),
  )

  async function add(files: File[]) {
    const done = await uploader.upload(files, { department: unit?.id ?? null })
    if (!done.length) return
    setExtra((e) => [...done, ...e])
    onUploaded()
    if (!multiple) onPick([done[0]])
    else
      setChosen((c) => {
        const room = max === undefined ? done.length : Math.max(0, max - c.length)
        return [...c, ...done.slice(0, room).map((d) => d.id)]
      })
  }

  const byId = new Map(all.map((i) => [i.id, i]))
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="image-filters">
        <Field label={t('Suchen')} type="search" value={q} onChange={(e) => setQ(e.target.value)} />
        <OrderField value={order} onChange={setOrder} />
        {(anyOther || unit) && (
          <fieldset className="image-scope">
            <legend className="sr-only">{t('Welche Bilder')}</legend>
            {unit && (
              <label>
                <input
                  type="radio"
                  name="bildumfang"
                  checked={scope === 'unit'}
                  onChange={() => setScope('unit')}
                />{' '}
                {t('nur')} {unit.name}
              </label>
            )}
            <label>
              <input
                type="radio"
                name="bildumfang"
                checked={scope === 'suggested'}
                onChange={() => setScope('suggested')}
              />{' '}
              {unit ? t('{name} und Verein allgemein', { name: unit.name }) : t('Verein allgemein')}
            </label>
            <label>
              <input
                type="radio"
                name="bildumfang"
                checked={scope === 'all'}
                onChange={() => setScope('all')}
              />{' '}
              {t('alle Bilder')}
            </label>
          </fieldset>
        )}
      </div>
      {uploader.dialog}
      {uploader.error && <Alert kind="error">{uploader.error}</Alert>}
      <p className="muted small">{t('Kopierte Bilder lassen sich mit Strg+V einfügen.')}</p>
      <ImageTiles
        images={filtered.slice(0, shown)}
        selected={multiple ? chosen : undefined}
        onClick={click}
        before={
          <li>
            <label className="image-tile image-tile-new">
              <span aria-hidden="true">＋</span>
              <span>{uploader.busy ? t('Wird hochgeladen …') : t('Neues Bild hochladen')}</span>
              <input
                type="file"
                accept={ACCEPT}
                multiple={multiple}
                className="sr-only"
                disabled={uploader.busy || (multiple && full)}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? [])
                  e.target.value = ''
                  if (files.length) void add(files)
                }}
              />
            </label>
          </li>
        }
      />
      {filtered.length === 0 && <p className="muted small">{t('Keine passenden Bilder.')}</p>}
      {filtered.length > shown && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setShown((n) => n + PAGE_SIZE)}
          >
            {t('Weitere laden')}
          </button>
        </div>
      )}
      <RightsHint />
      {multiple && (
        <div className="button-row">
          <button
            type="button"
            className="button button-primary"
            onClick={() => onPick(chosen.map((id) => byId.get(id)).filter((i) => !!i))}
          >
            {t('Übernehmen')}
            {max !== undefined ? t(' ({x0} von {x1})', { x0: chosen.length, x1: max }) : ''}
          </button>
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        </div>
      )}
    </Modal>
  )
}
