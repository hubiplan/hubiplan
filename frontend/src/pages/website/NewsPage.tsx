// Webseite › Aktuelles (#707): eigene Beiträge mit Titel, Datum (auch rückwirkend), Text,
// Bildern und Videos. Wie bei den Textseiten gibt es Entwurf und Veröffentlichen; die Webseite
// zeigt eigene Beiträge nach Datum gemischt mit denen aus Instagram und Facebook.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { contentApi, newsApi } from '../../api/website.ts'
import type { NewsPost, NewsVideo, WebsiteImage } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import {
  errorMessage,
  formatDate,
  formatDateTime,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading, SaveStatus, SelectField } from '../../components/ui.tsx'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ImageChoice } from './ImageChoice.tsx'
import { ImagePicker } from './ImagePicker.tsx'
import type { Unit } from './imagesHelpers.ts'
import { imageLabel } from './imageTools.ts'
import { t } from '../../i18n/index.ts'

const MAX_IMAGES = 20
const MAX_VIDEOS = 6

function status(p: NewsPost): string {
  if (!p.is_published) return t('Entwurf')
  return p.has_changes ? t('veröffentlicht, Entwurf geändert') : t('veröffentlicht')
}

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function NewsPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => newsApi.list(org.id), [org.id])
  const [open, setOpen] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  return (
    <div className="card card-wide">
      <h2>{t('Eigene Beiträge')}</h2>
      <p className="muted small">
        {t(
          'Hier schreibt ihr selbst Beiträge für „Aktuelles“: mit Titel, Datum, Text, Bildern und Videos. Das Datum darf auch weit zurückliegen, etwa für Beiträge einer früheren Webseite. Die Webseite zeigt sie nach Datum zusammen mit den Beiträgen aus Instagram und Facebook; ältere stehen im Archiv. Besucher sehen erst, was ihr veröffentlicht. Bilder lädst du unter',
        )}{' '}
        <Link to="/webseite/bilder">{t('Webseite › Bilder')}</Link>.
      </p>
      {data.posts.length === 0 && <p className="muted">{t('Noch keine eigenen Beiträge.')}</p>}
      <ul className="plain-list">
        {data.posts.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className="link-button"
              aria-expanded={open === p.id}
              onClick={() => setOpen(open === p.id ? null : p.id)}
            >
              {p.title}
            </button>
            <span className="muted small">
              {' '}
              · {formatDate(p.date)}
              {p.department_name && ` · ${p.department_name}`} · {status(p)}
            </span>
            {open === p.id && (
              <NewsForm
                key={p.id}
                post={p}
                units={data.units}
                onSaved={() => void reload()}
                onDeleted={() => {
                  setOpen(null)
                  void reload()
                }}
              />
            )}
          </li>
        ))}
      </ul>
      {adding ? (
        <NewNews
          onDone={(id) => {
            setAdding(false)
            if (id) setOpen(id)
            void reload()
          }}
        />
      ) : (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setAdding(true)}>
            {t('Neuer Beitrag')}
          </button>
        </div>
      )}
    </div>
  )
}

function NewNews({ onDone }: { onDone: (id: number | null) => void }) {
  const org = useActiveOrg()
  const form = useForm({ title: '', date: today() })
  const { values: v, set, errors } = form

  async function save() {
    const created = (await form.submit(() =>
      newsApi.create(org.id, { title: v.title, date: v.date }),
    )) as NewsPost | undefined
    if (created) onDone(created.id)
  }

  return (
    <form
      className="subcard"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <h3>{t('Neuer Beitrag')}</h3>
      <div className="grid-2">
        <Field
          label={t('Titel')}
          required
          value={v.title}
          error={errors.title}
          onChange={(e) => set('title', e.target.value)}
        />
        <Field
          label={t('Datum')}
          type="date"
          required
          value={v.date}
          error={errors.date}
          onChange={(e) => set('date', e.target.value)}
        />
      </div>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function NewsForm({
  post,
  units,
  onSaved,
  onDeleted,
}: {
  post: NewsPost
  units: Unit[]
  onSaved: () => void
  onDeleted: () => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    title: post.title,
    date: post.date,
    slug: post.slug,
    department: post.department,
    body: post.body,
    images: post.images,
    videos: post.videos,
  })
  const { values: v, set, errors } = form
  const [current, setCurrent] = useState(post)
  const auto = useAutoSave(form, (changes) => newsApi.save(org.id, post.id, changes), {
    onSaved: (saved) => setCurrent(saved as NewsPost),
  })
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  const [message, setMessage] = useState<string | null>(null)
  const unit: Unit | null = units.find((u) => u.id === v.department) ?? null
  const reloadImages = () => void images.reload()

  async function act(action: () => Promise<NewsPost>) {
    setMessage(null)
    if (!(await auto.flush())) return
    try {
      setCurrent(await action())
      onSaved()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('„{title}“ löschen?', { title: post.title }),
      message: t('Der Beitrag verschwindet von der Webseite.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await newsApi.remove(org.id, post.id)
      onDeleted()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <form
      className="subcard"
      onSubmit={(e) => e.preventDefault()}
      aria-label={t('Beitrag bearbeiten')}
    >
      <SaveStatus auto={auto} />
      <p className="muted small">
        {current.is_published
          ? t('Veröffentlicht am {x}.', { x: formatDateTime(current.published_at!) })
          : t('Noch nicht veröffentlicht.')}{' '}
        {current.is_published && current.has_changes && t('Der Entwurf hat Änderungen.')}
      </p>
      <div className="grid-2">
        <Field
          label={t('Titel')}
          value={v.title}
          error={errors.title}
          onChange={(e) => set('title', e.target.value)}
        />
        <Field
          label={t('Datum')}
          type="date"
          value={v.date}
          error={errors.date}
          hint={t('Auch rückwirkend; danach richtet sich die Reihenfolge.')}
          onChange={(e) => set('date', e.target.value)}
        />
      </div>
      <div className="grid-2">
        <Field
          label={t('Adresse')}
          value={v.slug}
          error={errors.slug}
          hint={t('Der Beitrag steht unter aktuelles/{slug}/.', { slug: v.slug })}
          onChange={(e) => set('slug', e.target.value)}
        />
        {units.length > 0 && (
          <SelectField
            label={t('Gehört zu')}
            value={v.department ?? ''}
            error={errors.department}
            hint={t('Beiträge einer Untereinheit erscheinen auf deren Seite.')}
            onChange={(e) => set('department', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('der ganzen Einheit')}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      <TextEditor
        label={t('Text')}
        value={v.body}
        error={errors.body}
        rows={10}
        images={images.data ?? []}
        renderImagePicker={(insert, cancel) => (
          <ImagePicker
            images={images.data ?? []}
            unit={unit}
            title={t('Bild einfügen')}
            onUploaded={reloadImages}
            onPick={(picked) => (picked[0] ? insert(picked[0]) : cancel())}
            onCancel={cancel}
          />
        )}
        onChange={(body) => set('body', body)}
      />
      <NewsImages
        images={images.data ?? []}
        value={v.images}
        error={errors.images}
        unit={unit}
        onChange={(ids) => set('images', ids)}
        onImagesChanged={reloadImages}
      />
      <NewsVideos
        images={images.data ?? []}
        value={v.videos}
        error={errors.videos}
        unit={unit}
        units={units}
        onChange={(videos) => set('videos', videos)}
        onImagesChanged={reloadImages}
      />
      {message && <Alert kind="error">{message}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          onClick={() => void act(() => newsApi.publish(org.id, post.id))}
        >
          {t('Veröffentlichen')}
        </button>
        {current.is_published && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void act(() => newsApi.unpublish(org.id, post.id))}
          >
            {t('Veröffentlichung zurücknehmen')}
          </button>
        )}
        <button type="button" className="button button-danger" onClick={() => void remove()}>
          {t('Löschen')}
        </button>
      </div>
    </form>
  )
}

/** Bilder unter dem Text: im Dialog ankreuzen, Reihenfolge hier ändern. */
function NewsImages({
  images,
  value,
  error,
  unit,
  onChange,
  onImagesChanged,
}: {
  images: WebsiteImage[]
  value: number[]
  error?: string
  unit: Unit | null
  onChange: (ids: number[]) => void
  onImagesChanged: () => void
}) {
  const [picking, setPicking] = useState(false)
  const byId = new Map(images.map((i) => [i.id, i]))
  const chosen = value.filter((id) => byId.has(id))
  const move = (index: number, delta: number) => {
    const next = [...chosen]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    onChange(next)
  }
  return (
    <fieldset className="gallery-picker">
      <legend>{t('Bilder (optional)')}</legend>
      <p className="muted small">
        {t(
          'Erscheinen unter dem Text; das erste Bild steht auch in der Übersicht. Bis zu {MAX_IMAGES} Bilder.',
          { MAX_IMAGES },
        )}
      </p>
      {chosen.length > 0 && (
        <ol className="gallery-list">
          {chosen.map((id, index) => (
            <li key={id}>
              <img src={byId.get(id)!.small_url} alt="" width={64} height={40} />
              <span>{imageLabel(byId.get(id)!)}</span>
              <span className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={index === 0}
                  aria-label={t('{x} nach vorn', { x: imageLabel(byId.get(id)!) })}
                  onClick={() => move(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={index === chosen.length - 1}
                  aria-label={t('{x} nach hinten', { x: imageLabel(byId.get(id)!) })}
                  onClick={() => move(index, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x} entfernen', { x: imageLabel(byId.get(id)!) })}
                  onClick={() => onChange(chosen.filter((x) => x !== id))}
                >
                  {t('Entfernen')}
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => setPicking(true)}>
          {chosen.length ? t('Bilder ändern') : t('Bilder wählen')}
        </button>
      </div>
      {picking && (
        <ImagePicker
          images={images}
          unit={unit}
          title={t('Bilder zum Beitrag')}
          multiple
          max={MAX_IMAGES}
          initial={chosen}
          onUploaded={onImagesChanged}
          onPick={(picked) => {
            setPicking(false)
            onChange(picked.map((i) => i.id))
          }}
          onCancel={() => setPicking(false)}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </fieldset>
  )
}

/** Videos als Link mit Vorschaubild; die Webseite bettet nichts ein. */
function NewsVideos({
  images,
  value,
  error,
  unit,
  units,
  onChange,
  onImagesChanged,
}: {
  images: WebsiteImage[]
  value: NewsVideo[]
  error?: string
  unit: Unit | null
  units: Unit[]
  onChange: (videos: NewsVideo[]) => void
  onImagesChanged: () => void
}) {
  const update = (index: number, patch: Partial<NewsVideo>) =>
    onChange(value.map((video, i) => (i === index ? { ...video, ...patch } : video)))
  return (
    <fieldset>
      <legend>{t('Videos (optional)')}</legend>
      <p className="muted small">
        {t(
          'Zum Beispiel von YouTube. Die Webseite zeigt ein Vorschaubild mit Link zum Video und bettet nichts ein, damit Besucher keinen Kontakt zu fremden Servern haben.',
        )}
      </p>
      {value.map((video, index) => (
        <div className="subcard" key={index}>
          <div className="grid-2">
            <Field
              label={t('Adresse des Videos')}
              type="url"
              placeholder="https://"
              value={video.url}
              onChange={(e) => update(index, { url: e.target.value })}
            />
            <Field
              label={t('Titel des Videos (optional)')}
              value={video.title}
              onChange={(e) => update(index, { title: e.target.value })}
            />
          </div>
          <ImageChoice
            label={t('Vorschaubild (optional)')}
            value={video.image}
            images={images}
            unit={unit}
            units={units}
            onChange={(id) => update(index, { image: id })}
            onImagesChanged={onImagesChanged}
          />
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              {t('Video entfernen')}
            </button>
          </div>
        </div>
      ))}
      {value.length < MAX_VIDEOS && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => onChange([...value, { url: 'https://', title: '', image: null }])}
          >
            {t('Video hinzufügen')}
          </button>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </fieldset>
  )
}
