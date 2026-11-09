// Galerie der Webseite (Ralf 05.11.2026): Alben mit Unteralben (z. B. „2024“ › „Schützenfest“),
// viele Fotos auf einmal hochladen, Bilder aus der Bilderverwaltung übernehmen, sortieren nach
// Aufnahmedatum, Dateiname … oder in eigener Reihenfolge per Ziehen.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { contentApi, galleryApi } from '../../api/website.ts'
import type {
  AlbumDraft,
  AlbumSort,
  GalleryAlbum,
  GalleryListing,
  ImageSort,
  WebsiteImage,
} from '../../api/website.ts'
import { ApiError } from '../../api/client.ts'
import { PERM } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { SortableList, SortHint } from '../../components/Sortable.tsx'
import { Alert, Checkbox, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ImageEditDialog, ImagePicker, ImageTiles, UploadButton } from './images.tsx'
import { droppedImages, imageLabel, useImageUpload } from './imageTools.ts'
import { t, tn } from '../../i18n/index.ts'

export function GalleryPage() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const open = Number(params.get('album')) || null
  const { data, error, reload } = useLoad(() => galleryApi.list(org.id), [org.id])

  function show(id: number | null) {
    const next = new URLSearchParams(params)
    if (id) next.set('album', String(id))
    else next.delete('album')
    setParams(next)
  }

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  if (open) {
    return (
      <AlbumEditor
        key={open}
        id={open}
        listing={data}
        onBack={() => {
          show(null)
          void reload()
        }}
        onOpen={show}
        onChanged={() => void reload()}
      />
    )
  }
  return <AlbumOverview listing={data} onOpen={show} onChanged={() => void reload()} />
}

// --- Übersicht ---

function AlbumOverview({
  listing,
  onOpen,
  onChanged,
}: {
  listing: GalleryListing
  onOpen: (id: number) => void
  onChanged: () => void
}) {
  const org = useActiveOrg()
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const canManage = org.permissions.includes(PERM.websiteManage)
  const top = listing.albums.filter((a) => !a.parent)
  const children = (id: number) => listing.albums.filter((a) => a.parent === id)

  async function create() {
    if (!title.trim()) return
    setBusy(true)
    setMessage(null)
    try {
      const album = await galleryApi.create(org.id, { title: title.trim() })
      setTitle('')
      onOpen(album.id)
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function setOrder(order: AlbumSort) {
    try {
      await galleryApi.setOrder(org.id, order)
      onChanged()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Galerie')}</h2>
      <p className="muted small">
        {t(
          'Fotoalben für die Webseite. Ein Album kann Unteralben haben, z. B. „2024“ mit „Schützenfest“ und „Königsball“. Auf der Webseite erscheint ein Album erst mit „Auf der Webseite zeigen“.',
        )}
      </p>
      {!listing.block_on && (
        <Alert kind="info">
          {t('Der Bereich „Galerie“ ist auf der Webseite noch ausgeschaltet.')}{' '}
          {canManage ? (
            <Link to="/webseite/aufbau">{t('Unter „Menü und Bereiche“ einschalten')}</Link>
          ) : (
            t('Einschalten kann, wer die Webseite verwaltet.')
          )}
        </Alert>
      )}
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <Field
          label={t('Neues Album')}
          value={title}
          maxLength={120}
          placeholder={t('z. B. 2024')}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button type="submit" className="button button-primary" disabled={busy || !title.trim()}>
          {t('Anlegen')}
        </button>
      </form>
      {message && <Alert kind="error">{message}</Alert>}
      {top.length === 0 ? (
        <p className="muted">{t('Noch keine Alben.')}</p>
      ) : (
        <>
          <SelectField
            label={t('Alben sortieren nach')}
            value={listing.gallery_order}
            onChange={(e) => void setOrder(e.target.value as AlbumSort)}
          >
            {listing.album_orders.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </SelectField>
          {listing.gallery_order === 'manual' ? (
            <>
              <SortHint website />
              <SortableList
                ariaLabel={t('Reihenfolge der Alben')}
                items={top}
                id={(a) => a.id}
                label={(a) => a.title}
                render={(a) => <AlbumRow album={a} onOpen={onOpen} />}
                onReorder={(ids) => galleryApi.reorder(org.id, ids, null).then(onChanged)}
              />
            </>
          ) : (
            <ul className="plain-list gallery-albums">
              {top.map((a) => (
                <li key={a.id}>
                  <AlbumRow album={a} onOpen={onOpen} />
                  {children(a.id).length > 0 && (
                    <ul className="plain-list gallery-subalbums">
                      {children(a.id).map((c) => (
                        <li key={c.id}>
                          <AlbumRow album={c} onOpen={onOpen} />
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function AlbumRow({ album, onOpen }: { album: GalleryAlbum; onOpen: (id: number) => void }) {
  return (
    <button type="button" className="gallery-album-row" onClick={() => onOpen(album.id)}>
      {album.cover_url ? (
        <img src={album.cover_url} alt="" loading="lazy" />
      ) : (
        <span className="gallery-album-empty" aria-hidden="true" />
      )}
      <span>
        <strong>{album.title}</strong>
        <span className="muted small">
          {' '}
          · {tn('{n} Bild', '{n} Bilder', album.image_count)}
          {album.date && ` · ${album.date.slice(0, 4)}`}
        </span>{' '}
        {!album.published && <small className="tag tag-muted">{t('nicht auf der Webseite')}</small>}
      </span>
    </button>
  )
}

// --- Album bearbeiten ---

function AlbumEditor({
  id,
  listing,
  onBack,
  onOpen,
  onChanged,
}: {
  id: number
  listing: GalleryListing
  onBack: () => void
  onOpen: (id: number | null) => void
  onChanged: () => void
}) {
  const org = useActiveOrg()
  const album = useLoad(() => galleryApi.get(org.id, id), [org.id, id])
  const library = useLoad(() => contentApi.images(org.id), [org.id])
  const [draft, setDraft] = useState<AlbumDraft | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [picking, setPicking] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [cropEach, setCropEach] = useState(false)
  const [dragging, setDragging] = useState(false)
  const uploader = useImageUpload()

  if (album.error) return <LoadError message={album.error} onRetry={() => void album.reload()} />
  const data = album.data
  if (!data) return <Loading />
  const form: AlbumDraft = draft ?? {
    title: data.title,
    slug: data.slug,
    description: data.description,
    date: data.date,
    parent: data.parent,
    published: data.published,
    show_captions: data.show_captions,
    image_order: data.image_order,
    children_order: data.children_order,
  }
  const images = data.images ?? []
  const subAlbums = listing.albums.filter((a) => a.parent === id)
  // Oberalbum: nur Hauptalben ohne eigenes Oberalbum, nicht das Album selbst
  const parents = listing.albums.filter((a) => !a.parent && a.id !== id)
  const set = (patch: AlbumDraft) => setDraft({ ...form, ...patch })

  async function apply(patch: AlbumDraft, done?: string) {
    setMessage(null)
    try {
      const saved = await galleryApi.save(org.id, id, patch)
      album.setData(saved)
      onChanged()
      if (done) setMessage({ kind: 'success', text: done })
      return true
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors)
      setMessage({ kind: 'error', text: errorMessage(err) })
      return false
    }
  }

  async function save() {
    setErrors({})
    if (await apply({ ...form, date: form.date || null }, t('Gespeichert.'))) setDraft(null)
  }

  async function addFiles(files: File[]) {
    const done = await uploader.upload(files, { cropEach })
    if (!done.length) return
    try {
      album.setData(
        await galleryApi.addImages(
          org.id,
          id,
          done.map((d) => d.id),
        ),
      )
      void library.reload()
      onChanged()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function addPicked(picked: WebsiteImage[]) {
    setPicking(false)
    if (!picked.length) return
    try {
      album.setData(
        await galleryApi.addImages(
          org.id,
          id,
          picked.map((p) => p.id),
        ),
      )
      onChanged()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function removeFromAlbum(image: WebsiteImage) {
    await apply({
      images: images.filter((i) => i.id !== image.id).map((i) => i.id),
      ...(data?.cover === image.id ? { cover: null } : {}),
    })
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Album „{name}“ löschen?', { name: data?.title ?? '' }),
      message: subAlbums.length
        ? t('Die Unteralben werden mit gelöscht. Die Bilder bleiben in der Bilderverwaltung.')
        : t('Die Bilder bleiben in der Bilderverwaltung.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await galleryApi.remove(org.id, id)
      onBack()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  const orderLabel = (o: { value: string; label: string }) => (
    <option key={o.value} value={o.value}>
      {o.label}
    </option>
  )

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
        if (files.length) void addFiles(files)
      }}
    >
      <p>
        <button type="button" className="button button-ghost" onClick={onBack}>
          ← {t('Alle Alben')}
        </button>
      </p>
      <h2>{data.title}</h2>
      <div className="form-grid">
        <Field
          label={t('Titel')}
          value={form.title ?? ''}
          maxLength={120}
          error={errors.title}
          onChange={(e) => set({ title: e.target.value })}
        />
        <Field
          label={t('Adresse')}
          value={form.slug ?? ''}
          maxLength={60}
          error={errors.slug}
          hint={t('auf der Webseite unter /galerie/{slug}/', { slug: form.slug ?? '' })}
          onChange={(e) => set({ slug: e.target.value })}
        />
        <Field
          label={t('Datum (optional)')}
          type="date"
          value={form.date ?? ''}
          error={errors.date}
          hint={t('Die Webseite zeigt das Jahr; danach lassen sich Alben sortieren.')}
          onChange={(e) => set({ date: e.target.value || null })}
        />
        {subAlbums.length === 0 && (
          <SelectField
            label={t('Gehört zu Album')}
            value={form.parent ? String(form.parent) : ''}
            error={errors.parent}
            onChange={(e) => set({ parent: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">{t('– Hauptalbum –')}</option>
            {parents.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      <div className="field">
        <label className="field-label" htmlFor="album-beschreibung">
          {t('Beschreibung (optional)')}
        </label>
        <textarea
          id="album-beschreibung"
          rows={3}
          maxLength={2000}
          value={form.description ?? ''}
          onChange={(e) => set({ description: e.target.value })}
        />
      </div>
      <Checkbox
        label={t('Auf der Webseite zeigen')}
        checked={!!form.published}
        onChange={(v) => set({ published: v })}
      />
      <Checkbox
        label={t('Bildunterschriften zeigen')}
        checked={!!form.show_captions}
        onChange={(v) => set({ show_captions: v })}
      />
      <div className="form-grid">
        <SelectField
          label={t('Bilder sortieren nach')}
          value={form.image_order}
          onChange={(e) => set({ image_order: e.target.value as ImageSort })}
        >
          {listing.image_orders.map(orderLabel)}
        </SelectField>
        {!form.parent && (
          <SelectField
            label={t('Unteralben sortieren nach')}
            value={form.children_order}
            onChange={(e) => set({ children_order: e.target.value as AlbumSort })}
          >
            {listing.album_orders.map(orderLabel)}
          </SelectField>
        )}
      </div>
      <div className="button-row">
        <button type="button" className="button button-primary" onClick={() => void save()}>
          {t('Speichern')}
        </button>
        {draft && (
          <button type="button" className="button button-ghost" onClick={() => setDraft(null)}>
            {t('Verwerfen')}
          </button>
        )}
        <button type="button" className="button button-danger" onClick={() => void remove()}>
          {t('Album löschen')}
        </button>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {!data.parent && (
        <>
          <h3>{t('Unteralben')}</h3>
          {subAlbums.length === 0 ? (
            <p className="muted small">
              {t(
                'Noch keine. Ein Unteralbum legst du an, indem du bei einem Album „Gehört zu Album“ wählst.',
              )}
            </p>
          ) : form.children_order === 'manual' && data.children_order === 'manual' ? (
            <SortableList
              ariaLabel={t('Reihenfolge der Unteralben')}
              items={subAlbums}
              id={(a) => a.id}
              label={(a) => a.title}
              render={(a) => <AlbumRow album={a} onOpen={(x) => onOpen(x)} />}
              onReorder={(ids) => galleryApi.reorder(org.id, ids, id).then(onChanged)}
            />
          ) : (
            <ul className="plain-list gallery-subalbums">
              {subAlbums.map((a) => (
                <li key={a.id}>
                  <AlbumRow album={a} onOpen={(x) => onOpen(x)} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <h3>{tn('{n} Bild', '{n} Bilder', images.length)}</h3>
      <p className="muted small">
        {t(
          'Fotos werden beim Hochladen verkleinert; Angaben wie Kamera oder Ort werden entfernt, das Aufnahmedatum wird zum Sortieren gemerkt. Du kannst Fotos auch hierher ziehen. Für Fotos mit Personen braucht es deren Einverständnis.',
        )}
      </p>
      <div className="button-row">
        <UploadButton
          label={t('Fotos hochladen')}
          disabled={uploader.working}
          onFiles={(files) => void addFiles(files)}
        />
        <button type="button" className="button" onClick={() => setPicking(true)}>
          {t('Aus der Bilderverwaltung wählen')}
        </button>
      </div>
      <Checkbox
        label={t('Jedes Foto vor dem Hochladen zuschneiden')}
        checked={cropEach}
        onChange={setCropEach}
      />
      {uploader.dialog}
      {uploader.progress && (
        <p className="muted small" aria-live="polite">
          {t('{n} von {m} Fotos hochgeladen …', {
            n: uploader.progress.done,
            m: uploader.progress.total,
          })}
        </p>
      )}
      {uploader.error && <Alert kind="error">{uploader.error}</Alert>}
      {images.length === 0 ? (
        <p className="muted">{t('Noch keine Bilder in diesem Album.')}</p>
      ) : data.image_order === 'manual' ? (
        <>
          <SortHint website />
          <SortableList
            ariaLabel={t('Reihenfolge der Bilder')}
            items={images}
            id={(i) => i.id}
            label={(i) => imageLabel(i)}
            render={(i) => (
              <ImageRow
                image={i}
                cover={data.cover === i.id}
                onEdit={() => setEditing(i.id)}
                onCover={() => void apply({ cover: i.id })}
                onRemove={() => void removeFromAlbum(i)}
              />
            )}
            onReorder={(ids) => apply({ images: ids })}
          />
        </>
      ) : (
        <>
          <p className="muted small">
            {t(
              'Für eine eigene Reihenfolge per Ziehen „Bilder sortieren nach: eigene Reihenfolge“ wählen.',
            )}
          </p>
          <ImageTiles images={images} onClick={(i) => setEditing(i.id)} />
          <ul className="plain-list small">
            {images.map((i) => (
              <li key={i.id}>
                <ImageRow
                  image={i}
                  cover={data.cover === i.id}
                  onEdit={() => setEditing(i.id)}
                  onCover={() => void apply({ cover: i.id })}
                  onRemove={() => void removeFromAlbum(i)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
      {picking && library.data && (
        <ImagePicker
          images={library.data.filter((i) => !images.some((x) => x.id === i.id))}
          title={t('Bilder für das Album wählen')}
          multiple
          onUploaded={() => void library.reload()}
          onPick={(picked) => void addPicked(picked)}
          onCancel={() => setPicking(false)}
        />
      )}
      {editing !== null && (
        <ImageEditDialog
          id={editing}
          units={[]}
          onChanged={() => void album.reload()}
          onOpen={setEditing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

function ImageRow({
  image,
  cover,
  onEdit,
  onCover,
  onRemove,
}: {
  image: WebsiteImage
  cover: boolean
  onEdit: () => void
  onCover: () => void
  onRemove: () => void
}) {
  return (
    <span className="gallery-image-row">
      <img src={image.small_url} alt="" loading="lazy" />
      <span>{imageLabel(image)}</span>
      {cover ? (
        <small className="tag">{t('Titelbild')}</small>
      ) : (
        <button type="button" className="button button-ghost" onClick={onCover}>
          {t('Als Titelbild')}
        </button>
      )}
      <button type="button" className="button button-ghost" onClick={onEdit}>
        {t('Bearbeiten')}
      </button>
      <button type="button" className="button button-ghost" onClick={onRemove}>
        {t('Aus dem Album nehmen')}
      </button>
    </span>
  )
}
