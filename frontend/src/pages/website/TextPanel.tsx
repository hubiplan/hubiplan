import { sendingVersion } from '../../api/client.ts'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { contentApi } from '../../api/website.ts'
import type {
  LinkTarget,
  PageSectionOptions,
  WebsiteImage,
  WebsiteText,
} from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import {
  errorMessage,
  formatDateTime,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SaveStatus,
  SelectField,
  Loading,
} from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { PERM } from '../../api/orgs.ts'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { ImageChoice } from './ImageChoice.tsx'
import { ImagePicker } from './ImagePicker.tsx'
import { HomeBuilder } from './HomeBuilder.tsx'
import { TimelineEditor } from './TimelineEditor.tsx'
import { normalizeEntry } from './timeline.ts'
import { imageLabel } from './imageTools.ts'
import type { Unit } from './imagesHelpers.ts'
import { t } from '../../i18n/index.ts'

export function TextPanel({
  id,
  units,
  linkTargets,
  onChanged,
  onDeleted,
  chronicle = false,
  sectionOptions,
}: {
  id: number
  units: Unit[]
  linkTargets: LinkTarget[]
  /** Auswahl für die Abschnitte der Textseiten (G4) */
  sectionOptions?: PageSectionOptions
  onChanged: () => void
  onDeleted: () => void
  /** Menüpunkt „Chronik“: ohne Adresse, Menü und Löschen (gehören zur Webseite) */
  chronicle?: boolean
}) {
  const org = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => contentApi.text(org.id, id), [org.id, id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  return (
    <TextForm
      key={`${data.id}-${data.updated_at}-${data.revisions.length}`}
      text={data}
      units={units}
      linkTargets={linkTargets}
      chronicle={chronicle}
      sectionOptions={sectionOptions}
      onSaved={(tm) => {
        setData(tm)
        onChanged()
      }}
      onDeleted={onDeleted}
    />
  )
}

function TextForm({
  text,
  units,
  linkTargets,
  chronicle,
  sectionOptions,
  onSaved,
  onDeleted,
}: {
  text: WebsiteText
  units: Unit[]
  linkTargets: LinkTarget[]
  chronicle: boolean
  sectionOptions?: PageSectionOptions
  onSaved: (tm: WebsiteText) => void
  onDeleted: () => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    title: text.title,
    slug: text.slug,
    show_in_menu: text.show_in_menu,
    body: text.body,
    image: text.image,
    gallery: text.gallery ?? [],
    gallery_interval: text.gallery_interval ?? 7,
    gallery_random: text.gallery_random ?? false,
    show_captions: text.show_captions ?? false,
    timeline: (text.timeline ?? []).map(normalizeEntry),
    timeline_newest_first: text.timeline_newest_first ?? false,
    sections: text.sections ?? [],
    hide_after_event: text.hide_after_event ?? false,
  })
  const { values: v, set, errors } = form
  const [current, setCurrent] = useState(text)
  const auto = useAutoSave(form, (changes) => contentApi.save(org.id, text.id, changes), {
    version: text.version,
    onSaved: (saved) => setCurrent(saved as WebsiteText),
  })
  const images = useLoad(() => contentApi.images(org.id), [org.id])
  const [message, setMessage] = useState<string | null>(null)
  // Text einer Untereinheit: in der Bildauswahl stehen deren Bilder vorn
  const unit: Unit | null =
    text.kind === 'unit' && text.department
      ? (units.find((u) => u.id === text.department) ?? {
          id: text.department,
          name: text.department_name ?? t('Untereinheit'),
        })
      : null
  const reloadImages = () => void images.reload()

  async function act(action: () => Promise<WebsiteText>) {
    setMessage(null)
    if (!(await auto.flush())) return
    try {
      // Veröffentlichen und Zurückholen gelten für die Fassung, die hier offen ist
      const result = await sendingVersion(auto.version(), action)
      auto.resetVersion(result.version)
      onSaved(result)
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('„{title}“ löschen?', { title: text.title }),
      message: t('Die Seite verschwindet von der Webseite, frühere Fassungen werden mit gelöscht.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await sendingVersion(auto.version(), () => contentApi.remove(org.id, text.id))
      onDeleted()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  // Gilt für das einzelne Bild und das Karussell (Ralf 02.11., Standard aus)
  const captionsBox = (
    <Checkbox
      label={t('Bildunterschriften auf der Webseite zeigen')}
      hint={
        text.kind === 'page' || text.kind === 'intro'
          ? t('Gilt für das Bild oben auf der Seite.')
          : t('Gilt für das einzelne Bild und für das Bilderkarussell.')
      }
      checked={v.show_captions}
      onChange={(on) => set('show_captions', on)}
    />
  )

  // Abschnitte der Seite (G4); seit #491 auch auf den Seiten der Untereinheiten
  const sectionsBox = (text.kind === 'page' || text.kind === 'unit') &&
    !text.has_timeline &&
    text.sections &&
    sectionOptions && (
      <section className="field" aria-labelledby={`abschnitte-${text.id}`}>
        <h3 id={`abschnitte-${text.id}`}>{t('Abschnitte der Seite')}</h3>
        <p className="muted small">
          {text.kind === 'unit'
            ? t(
                'Über und unter dem Text kannst du weitere Abschnitte einfügen, etwa Text mit Bild, Bilder, ein Zitat oder Trainingszeiten. Kontakt, Homepage, Termine und die anderen festen Blöcke lassen sich verschieben und ausblenden. Alles erscheint mit „Veröffentlichen“.',
              )
            : t(
                'Über und unter dem Text kannst du weitere Abschnitte einfügen, etwa ein Banner, Knöpfe oder Kacheln. Sie erscheinen mit „Veröffentlichen“.',
              )}
        </p>
        <HomeBuilder
          data={sectionOptions}
          website={sectionOptions}
          value={v.sections}
          blocks={sectionOptions.blocks}
          design=""
          page
          onChange={(next) => set('sections', next)}
        />
      </section>
    )

  // Chronik mit Modul „Chronik“: Inhalt nur unter Vereinsleben › Chronik pflegen (Ralf 09.11.),
  // hier bleibt nur, was zur Webseite gehört (Adresse, Menü, Löschen).
  if (text.has_timeline && !chronicle) {
    return (
      <form
        className="subcard"
        onSubmit={(e) => e.preventDefault()}
        aria-label={t('Text bearbeiten')}
      >
        <SaveStatus auto={auto} />
        <p className="muted small">
          {current.is_published
            ? t('Veröffentlicht am {x}.', { x: formatDateTime(current.published_at!) })
            : t('Noch nicht veröffentlicht.')}{' '}
          {current.is_published && current.has_changes && t('Der Entwurf hat Änderungen.')}
        </p>
        <Alert kind="info">
          {t('Einleitung und Zeitleiste der Chronik pflegst du unter Vereinsleben › Chronik.')}{' '}
          {org.permissions.includes(PERM.chronicleView) && (
            <Link to="/chronik">{t('Zur Chronik')}</Link>
          )}
        </Alert>
        <div className="grid-2">
          <Field
            label={t('Adresse')}
            value={v.slug}
            error={errors.slug}
            onChange={(e) => set('slug', e.target.value)}
          />
          <Checkbox
            label={t('im Menü zeigen')}
            checked={v.show_in_menu}
            onChange={(on) => set('show_in_menu', on)}
          />
        </div>
        {message && <Alert kind="error">{message}</Alert>}
        <div className="button-row">
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Löschen')}
          </button>
        </div>
      </form>
    )
  }

  return (
    <form
      className="subcard"
      onSubmit={(e) => e.preventDefault()}
      aria-label={t('Text bearbeiten')}
    >
      <SaveStatus auto={auto} />
      <p className="muted small">
        {current.is_published
          ? t('Veröffentlicht am {x}.', { x: formatDateTime(current.published_at!) })
          : t('Noch nicht veröffentlicht.')}{' '}
        {current.is_published && current.has_changes && t('Der Entwurf hat Änderungen.')}
      </p>
      {text.kind === 'intro' ? (
        <p className="muted small">
          {t('Erscheint oben im Bereich „{x}“, über dem Inhalt aus HUBIplan.', {
            x: text.area_label || text.slug,
          })}
        </p>
      ) : (
        <Field
          label={t('Titel')}
          value={v.title}
          error={errors.title}
          onChange={(e) => set('title', e.target.value)}
        />
      )}
      {text.kind === 'page' && !chronicle && (
        <div className="grid-2">
          <Field
            label={t('Adresse')}
            value={v.slug}
            error={errors.slug}
            onChange={(e) => set('slug', e.target.value)}
          />
          <Checkbox
            label={t('im Menü zeigen')}
            checked={v.show_in_menu}
            onChange={(on) => set('show_in_menu', on)}
          />
        </div>
      )}
      {text.kind === 'page' && text.event && (
        <section className="field" aria-labelledby={`veranstaltung-${text.id}`}>
          <h3 id={`veranstaltung-${text.id}`}>{t('Veranstaltungsseite')}</h3>
          <p className="muted small">
            {t(
              'Gehört zum Termin „{title}“ am {when}. Datum, Ort, Programm, Preise, freie Plätze und der Knopf zur Anmeldung kommen aus dem Termin und erscheinen oben auf der Seite. Hier pflegst du nur Text und Abschnitte darunter.',
              { title: text.event.title, when: formatDateTime(text.event.starts_at) },
            )}
          </p>
          {!text.event.is_public && (
            <Alert kind="info">
              {t(
                'Der Termin ist nicht mehr „nach außen öffentlich“. Die Seite zeigt deshalb keine Eckdaten und keinen Anmeldeknopf.',
              )}
            </Alert>
          )}
          <Checkbox
            label={t('Nach dem Ende der Veranstaltung von der Webseite nehmen')}
            hint={t(
              'Der Menüpunkt verschwindet in jedem Fall am Tag nach dem Ende. Ohne Haken bleibt die Seite als Rückblick erreichbar.',
            )}
            checked={v.hide_after_event}
            onChange={(on) => set('hide_after_event', on)}
          />
        </section>
      )}
      {text.has_timeline && (
        <p className="muted small">
          {t(
            'Der Text steht oben auf der Seite, darunter die Zeitleiste. Für die Chronik genügen meist ein paar einleitende Sätze.',
          )}
        </p>
      )}
      <TextEditor
        label={text.has_timeline ? t('Einleitung (optional)') : t('Text')}
        value={v.body}
        error={errors.body}
        rows={12}
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
        linkTargets={linkTargets}
        onChange={(body) => set('body', body)}
      />
      <ImageChoice
        label={text.kind === 'unit' ? t('Bild der Untereinheit') : t('Bild oben auf der Seite')}
        value={v.image}
        images={images.data ?? []}
        unit={unit}
        units={units}
        onChange={(id) => set('image', id)}
        onImagesChanged={reloadImages}
      />
      {(text.kind === 'page' || text.kind === 'intro') && captionsBox}
      {text.kind === 'page' && sectionsBox}
      {text.has_timeline && (
        <TimelineEditor
          textId={text.id}
          value={v.timeline}
          error={errors.timeline}
          images={images.data ?? []}
          onChange={(entries) => set('timeline', entries)}
          newestFirst={v.timeline_newest_first}
          onNewestFirstChange={(value) => set('timeline_newest_first', value)}
          onImagesChanged={reloadImages}
        />
      )}
      {(text.kind === 'greeting' || text.kind === 'unit') && (
        <GalleryPicker
          images={images.data ?? []}
          value={v.gallery}
          error={errors.gallery}
          unit={unit}
          interval={v.gallery_interval}
          intervalError={errors.gallery_interval}
          onIntervalChange={(seconds) => set('gallery_interval', seconds)}
          random={v.gallery_random}
          onRandomChange={(on) => set('gallery_random', on)}
          onChange={(ids) => set('gallery', ids)}
          onImagesChanged={reloadImages}
        />
      )}
      {(text.kind === 'greeting' || text.kind === 'unit') && captionsBox}
      {text.kind === 'unit' && sectionsBox}
      {message && <Alert kind="error">{message}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          onClick={() => void act(() => contentApi.publish(org.id, text.id))}
        >
          {t('Veröffentlichen')}
        </button>
        {current.is_published && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => void act(() => contentApi.unpublish(org.id, text.id))}
          >
            {t('Veröffentlichung zurücknehmen')}
          </button>
        )}
        {text.kind !== 'greeting' && !chronicle && (
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Löschen')}
          </button>
        )}
      </div>
      {text.revisions.length > 0 && (
        <>
          <h4>{t('Frühere Fassungen')}</h4>
          <ul className="plain-list">
            {text.revisions.map((r) => (
              <li key={r.id}>
                {formatDateTime(r.published_at)}
                {r.published_by && t(' · {published_by}', { published_by: r.published_by })}{' '}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void act(() => contentApi.restore(org.id, text.id, r.id))}
                >
                  {t('In den Entwurf holen')}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </form>
  )
}

const MAX_GALLERY = 10
const MIN_INTERVAL = 3
const MAX_INTERVAL = 30

/** Bilderkarussell: Bilder im Auswahl-Dialog ankreuzen, Reihenfolge hier ändern */
function GalleryPicker({
  images,
  value,
  error,
  unit,
  interval,
  intervalError,
  onIntervalChange,
  random,
  onRandomChange,
  onChange,
  onImagesChanged,
}: {
  images: WebsiteImage[]
  value: number[]
  error?: string
  unit: Unit | null
  interval: number
  intervalError?: string
  onIntervalChange: (seconds: number) => void
  random: boolean
  onRandomChange: (on: boolean) => void
  onChange: (ids: number[]) => void
  onImagesChanged: () => void
}) {
  const [picking, setPicking] = useState(false)
  const [seconds, setSeconds] = useState(String(interval))
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
      <legend>{t('Bilderkarussell (optional)')}</legend>
      <p className="muted small">
        {t(
          'Mit zwei oder mehr Bildern zeigt die Startseite statt des einzelnen Bildes ein Karussell zum Durchblättern. Es wechselt von selbst und lässt sich anhalten. Bis zu {MAX_GALLERY} Bilder.',
          { MAX_GALLERY },
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
      {chosen.length > 1 && (
        <div className="grid-2">
          <SelectField
            label={t('Beginnt mit')}
            value={random ? 'random' : 'first'}
            hint={random ? undefined : t('Das erste Bild legst du mit ↑ ↓ fest.')}
            onChange={(e) => onRandomChange(e.target.value === 'random')}
          >
            <option value="first">{t('dem ersten Bild der Liste')}</option>
            <option value="random">{t('einem zufälligen Bild')}</option>
          </SelectField>
          <Field
            label={t('Nächstes Bild nach (Sekunden)')}
            type="number"
            inputMode="numeric"
            className="gallery-interval"
            min={MIN_INTERVAL}
            max={MAX_INTERVAL}
            step={1}
            value={seconds}
            hint={t('{MIN_INTERVAL} bis {MAX_INTERVAL} Sekunden, Standard 7.', {
              MIN_INTERVAL,
              MAX_INTERVAL,
            })}
            error={intervalError}
            onChange={(e) => {
              // Erst gültige Werte übernehmen, damit Tippen nicht zwischendurch speichert
              setSeconds(e.target.value)
              const n = Number(e.target.value)
              if (Number.isInteger(n) && n >= MIN_INTERVAL && n <= MAX_INTERVAL) onIntervalChange(n)
            }}
            onBlur={() => setSeconds(String(interval))}
          />
        </div>
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
          title={t('Bilder fürs Karussell')}
          multiple
          max={MAX_GALLERY}
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
