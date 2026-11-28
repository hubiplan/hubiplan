import { useState } from 'react'
import { contentApi } from '../../api/website.ts'
import { useLoad } from '../../components/forms.ts'
import { RightsHint } from '../../components/RightsHint.tsx'
import { Alert, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { Why } from '../../learning/Aids.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { droppedImages, sortImages, useImageUpload, usePasteImages } from './imageTools.ts'
import type { ImageOrder } from './imageTools.ts'
import { t, tn } from '../../i18n/index.ts'
import { PAGE_SIZE, matches, type Scope, type State } from './imagesHelpers.ts'
import { UploadButton } from './UploadButton.tsx'
import { OrderField } from './OrderField.tsx'
import { ImageEditDialog } from './ImageEditDialog.tsx'
import { ImageTiles } from './ImageTiles.tsx'

export function ImagesPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => contentApi.images(org.id), [org.id])
  const texts = useLoad(() => contentApi.texts(org.id), [org.id])
  const units = texts.data?.units ?? []
  const [q, setQ] = useState('')
  const [scope, setScope] = useState<Scope>('all')
  const [state, setState] = useState<State>('all')
  const [order, setOrder] = useState<ImageOrder>('newest')
  const [shown, setShown] = useState(PAGE_SIZE)
  const [open, setOpen] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const uploader = useImageUpload()

  async function add(files: File[]) {
    const done = await uploader.upload(files, {
      department: typeof scope === 'number' ? scope : null,
    })
    if (done.length) void reload()
    if (done.length === 1) setOpen(done[0].id)
  }
  usePasteImages(open === null && !uploader.working, (files) => void add(files))

  const all = data ?? []
  const filtered = sortImages(
    all.filter((i) => matches(i, q, scope, state)),
    order,
  )
  const scopeValue = typeof scope === 'number' ? String(scope) : scope

  return (
    <div
      className={`card card-wide${dragging ? ' drop-target' : ''}`}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer.types).includes('Files')) {
          e.preventDefault()
          setDragging(true)
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const files = droppedImages(e)
        if (files.length) void add(files)
      }}
    >
      <h2>{t('Bilder')}</h2>
      <div className="aid-row">
        <Why k="web_photos" />
        <Why k="web_alt_text" />
        <Why k="image_credit" />
      </div>
      <p className="muted small">
        {t(
          'Bilder werden beim Hochladen verkleinert, und Angaben wie Kamera oder Aufnahmeort werden entfernt. Für Fotos mit Personen braucht es deren Einverständnis. Du kannst Bilder auch hierher ziehen oder kopierte Bilder mit Strg+V einfügen. Ein Klick auf ein Bild öffnet es zum Bearbeiten.',
        )}
      </p>
      <RightsHint />
      <div className="image-filters">
        <Field
          label={t('Suchen')}
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setShown(PAGE_SIZE)
          }}
        />
        {units.length > 0 && (
          <SelectField
            label={t('Gehört zu')}
            value={scopeValue}
            onChange={(e) => {
              const v = e.target.value
              setScope(v === 'all' || v === 'general' ? v : Number(v))
              setShown(PAGE_SIZE)
            }}
          >
            <option value="all">{t('alle')}</option>
            <option value="general">{t('Verein allgemein')}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField
          label={t('Zustand')}
          value={state}
          onChange={(e) => {
            setState(e.target.value as State)
            setShown(PAGE_SIZE)
          }}
        >
          <option value="all">{t('alle')}</option>
          <option value="unused">{t('nicht verwendet')}</option>
          <option value="no_alt">{t('ohne Beschreibung')}</option>
        </SelectField>
        <OrderField value={order} onChange={setOrder} />
        <div className="button-row">
          <UploadButton disabled={uploader.busy} onFiles={(files) => void add(files)} />
        </div>
      </div>
      {uploader.dialog}
      {uploader.busy && <p className="muted small">{t('Wird hochgeladen …')}</p>}
      {uploader.error && <Alert kind="error">{uploader.error}</Alert>}
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {data && all.length === 0 && <p className="muted">{t('Noch keine Bilder hochgeladen.')}</p>}
      {data && all.length > 0 && (
        <p className="muted small" aria-live="polite">
          {filtered.length === all.length
            ? tn('{n} Bild', '{n} Bilder', all.length)
            : t('{n} von {n2} Bildern', { n: filtered.length, n2: all.length })}
        </p>
      )}
      <ImageTiles images={filtered.slice(0, shown)} onClick={(i) => setOpen(i.id)} />
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
      {open !== null && (
        <ImageEditDialog
          id={open}
          units={units}
          onChanged={() => void reload()}
          onOpen={setOpen}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

// --- Bild bearbeiten ---
