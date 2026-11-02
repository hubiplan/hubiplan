// Zeitleiste der Chronik: kurze Einträge mit Jahr oder Zeitraum statt einer Textwand.
import { useState } from 'react'
import { contentApi } from '../../api/website.ts'
import type { TimelineEntry, WebsiteImage } from '../../api/website.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t, tn } from '../../i18n/index.ts'
import { ImagePicker } from './images.tsx'
import { imageLabel } from './imageTools.ts'
import {
  EMPTY,
  MAX_IMAGES,
  MAX_TEXT,
  MAX_TIMELINE,
  MAX_TITLE,
  entryErrors,
  periodLabel,
  sortTimeline,
  yearValue,
} from './timeline.ts'

export function TimelineEditor({
  textId,
  value,
  error,
  images,
  onChange,
  onImagesChanged,
  newestFirst,
  onNewestFirstChange,
}: {
  textId: number
  value: TimelineEntry[]
  error?: string
  images: WebsiteImage[]
  onChange: (entries: TimelineEntry[]) => void
  onImagesChanged: () => void
  newestFirst: boolean
  onNewestFirstChange: (value: boolean) => void
}) {
  const org = useActiveOrg()
  // Nummer des bearbeiteten Eintrags, -1 = neues Ereignis, -2 = neues Kapitel
  const [editing, setEditing] = useState<number | null>(null)
  const [importing, setImporting] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [importErrors, setImportErrors] = useState<{ line: number; message: string }[]>([])
  const [fileKey, setFileKey] = useState(0)
  const byId = new Map(images.map((i) => [i.id, i]))

  function apply(entry: TimelineEntry) {
    const clean = { ...entry, title: entry.title.trim(), text: entry.text.trim() }
    if (clean.until === clean.year) clean.until = null
    if (clean.kind === 'chapter') clean.images = []
    const next =
      editing === null || editing < 0
        ? [...value, clean]
        : value.map((e, i) => (i === editing ? clean : e))
    onChange(sortTimeline(next))
    setEditing(null)
  }

  async function importFile(file: File | undefined) {
    if (!file) return
    setImporting(true)
    setNotice(null)
    setImportErrors([])
    try {
      const result = await contentApi.importTimeline(org.id, textId, file)
      const key = (e: TimelineEntry) => `${e.kind}|${e.year}|${e.until ?? ''}|${e.title}`
      const known = new Set(value.map(key))
      const fresh = result.entries.filter((e) => !known.has(key(e)))
      const room = MAX_TIMELINE - value.length
      const taken = fresh.slice(0, Math.max(room, 0))
      if (taken.length) onChange(sortTimeline([...value, ...taken]))
      const skipped = result.entries.length - fresh.length
      const parts = [tn('{n} Eintrag übernommen.', '{n} Einträge übernommen.', taken.length)]
      if (skipped) parts.push(t('{n} gab es schon.', { n: skipped }))
      if (fresh.length > taken.length)
        parts.push(t('Mehr als {n} Einträge passen nicht in die Zeitleiste.', { n: MAX_TIMELINE }))
      if (result.errors.length)
        parts.push(
          tn(
            '{n} Zeile wurde wegen Fehlern nicht übernommen:',
            '{n} Zeilen wurden wegen Fehlern nicht übernommen:',
            result.errors.length,
          ),
        )
      setNotice({ kind: result.errors.length ? 'error' : 'success', text: parts.join(' ') })
      setImportErrors(result.errors)
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
    } finally {
      setImporting(false)
      setFileKey((k) => k + 1)
    }
  }

  return (
    <fieldset className="gallery-picker timeline-editor">
      <legend>{t('Zeitleiste')}</legend>
      <p className="muted small">
        {t(
          'Kurze Einträge mit Jahr oder Zeitraum (z. B. 1939 bis 1948). Die Webseite zeigt sie nach Jahren sortiert an einer Linie, mit Bild zum Vergrößern. Text höchstens {n} Zeichen, damit keine Textwand entsteht. Veröffentlicht wird die Zeitleiste zusammen mit der Chronik.',
          { n: MAX_TEXT },
        )}{' '}
        {t(
          'Kapitel (z. B. „Gründerjahre 1920–1938“) sind Zwischenüberschriften: Alle Ereignisse ab ihrem Jahr stehen darunter, bis das nächste Kapitel beginnt.',
        )}
      </p>
      <Checkbox
        label={t('Neueste Einträge oben')}
        hint={t(
          'Die Webseite zeigt die Zeitleiste dann vom heutigen Jahr rückwärts; Kapitel stehen weiter über ihren Ereignissen.',
        )}
        checked={newestFirst}
        onChange={onNewestFirstChange}
      />
      {value.length > 0 && (
        <ol className="timeline-list">
          {value.map((e, index) =>
            editing === index ? (
              <li key={`edit-${index}`}>
                <EntryForm
                  initial={e}
                  images={images}
                  onApply={apply}
                  onCancel={() => setEditing(null)}
                  onImagesChanged={onImagesChanged}
                />
              </li>
            ) : (
              <li
                key={`${index}-${e.year}-${e.title}`}
                className={e.kind === 'chapter' ? 'timeline-chapter' : undefined}
              >
                <strong className="timeline-period">{periodLabel(e)}</strong>
                <span className="timeline-summary">
                  <span>
                    {e.kind === 'chapter' && <span className="badge">{t('Kapitel')}</span>}{' '}
                    {e.title}
                  </span>
                  {e.text && <small className="muted">{e.text}</small>}
                </span>
                {e.images.some((id) => byId.has(id)) && (
                  <span className="timeline-thumbs">
                    {e.images
                      .filter((id) => byId.has(id))
                      .map((id) => (
                        <img key={id} src={byId.get(id)!.small_url} alt="" width={64} height={40} />
                      ))}
                  </span>
                )}
                <span className="button-row">
                  <button
                    type="button"
                    className="button button-ghost"
                    aria-label={t('{x} bearbeiten', { x: `${periodLabel(e)} ${e.title}` })}
                    disabled={editing !== null}
                    onClick={() => setEditing(index)}
                  >
                    {t('Bearbeiten')}
                  </button>
                  <button
                    type="button"
                    className="button button-ghost"
                    aria-label={t('{x} entfernen', { x: `${periodLabel(e)} ${e.title}` })}
                    disabled={editing !== null}
                    onClick={() => onChange(value.filter((_, i) => i !== index))}
                  >
                    {t('Entfernen')}
                  </button>
                </span>
              </li>
            ),
          )}
        </ol>
      )}
      {editing !== null && editing < 0 && (
        <EntryForm
          initial={editing === -2 ? { ...EMPTY, kind: 'chapter' } : EMPTY}
          images={images}
          onApply={apply}
          onCancel={() => setEditing(null)}
          onImagesChanged={onImagesChanged}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {importErrors.length > 0 && (
        <ul className="small">
          {importErrors.slice(0, 20).map((e) => (
            <li key={e.line}>{t('Zeile {line}: {message}', e)}</li>
          ))}
        </ul>
      )}
      {editing === null && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={value.length >= MAX_TIMELINE}
            onClick={() => setEditing(-1)}
          >
            {t('Ereignis hinzufügen')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={value.length >= MAX_TIMELINE}
            onClick={() => setEditing(-2)}
          >
            {t('Kapitel hinzufügen')}
          </button>
          <label className="button button-ghost">
            {importing ? t('Liest …') : t('Aus Excel übernehmen')}
            <input
              key={fileKey}
              type="file"
              className="sr-only"
              accept=".xlsx,.xlsm,.csv,.txt"
              disabled={importing}
              onChange={(ev) => void importFile(ev.target.files?.[0])}
            />
          </label>
        </div>
      )}
      <p className="muted small">
        {t(
          'Excel oder CSV mit den Spalten Jahr, Überschrift und optional bis, Text und Art („Kapitel“ für ein Kapitel, sonst leer). Die Einträge kommen in den Entwurf und lassen sich dort noch ändern.',
        )}
      </p>
    </fieldset>
  )
}

function EntryForm({
  initial,
  images: allImages,
  onApply,
  onCancel,
  onImagesChanged,
}: {
  initial: TimelineEntry
  images: WebsiteImage[]
  onApply: (entry: TimelineEntry) => void
  onCancel: () => void
  onImagesChanged: () => void
}) {
  const [year, setYear] = useState(initial.year === null ? '' : String(initial.year))
  const [until, setUntil] = useState(initial.until === null ? '' : String(initial.until))
  const [title, setTitle] = useState(initial.title)
  const [text, setText] = useState(initial.text)
  const [images, setImages] = useState<number[]>(initial.images)
  const [checked, setChecked] = useState(false)
  const chapter = initial.kind === 'chapter'
  const entry: TimelineEntry = {
    kind: initial.kind,
    year: yearValue(year),
    until: until.trim() ? (yearValue(until) ?? -1) : null,
    title,
    text,
    images,
  }
  const errors = checked ? entryErrors(entry) : {}

  function submit() {
    setChecked(true)
    if (Object.keys(entryErrors(entry)).length === 0) onApply(entry)
  }

  return (
    <div
      className="subcard timeline-form"
      role="group"
      aria-label={
        chapter
          ? initial.title
            ? t('Kapitel bearbeiten')
            : t('Neues Kapitel')
          : initial.title
            ? t('Ereignis bearbeiten')
            : t('Neues Ereignis')
      }
    >
      <div className="grid-2">
        <Field
          label={chapter ? t('Beginnt im Jahr') : t('Jahr')}
          inputMode="numeric"
          value={year}
          error={errors.year}
          autoFocus
          onChange={(e) => setYear(e.target.value)}
        />
        <Field
          label={t('bis (optional)')}
          inputMode="numeric"
          value={until}
          error={errors.until}
          hint={
            chapter
              ? t('Ende des Kapitels, z. B. 1938')
              : t('für einen Zeitraum, z. B. 1939 bis 1948')
          }
          onChange={(e) => setUntil(e.target.value)}
        />
      </div>
      <Field
        label={chapter ? t('Name des Kapitels') : t('Überschrift')}
        value={title}
        error={errors.title}
        maxLength={MAX_TITLE}
        onChange={(e) => setTitle(e.target.value)}
      />
      <TextArea value={text} error={errors.text} onChange={setText} />
      {!chapter && (
        <ImagesChoice
          value={images}
          images={allImages}
          onChange={setImages}
          onImagesChanged={onImagesChanged}
        />
      )}
      <div className="button-row">
        <button type="button" className="button button-primary" onClick={submit}>
          {t('Übernehmen')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </div>
  )
}

function TextArea({
  value,
  error,
  onChange,
}: {
  value: string
  error?: string
  onChange: (text: string) => void
}) {
  const id = 'timeline-text'
  const count = t('{n} von {max} Zeichen', { n: value.length, max: MAX_TEXT })
  return (
    <div className={`field${error ? ' field-invalid' : ''}`}>
      <label className="field-label" htmlFor={id}>
        {t('Text (optional)')}
      </label>
      <textarea
        id={id}
        rows={3}
        value={value}
        maxLength={MAX_TEXT}
        aria-invalid={!!error}
        aria-describedby={`${id}-hinweis`}
        onChange={(e) => onChange(e.target.value)}
      />
      <small className={error ? 'field-error' : 'muted'} id={`${id}-hinweis`}>
        {error ?? count}
      </small>
    </div>
  )
}

function ImagesChoice({
  value,
  images,
  onChange,
  onImagesChanged,
}: {
  value: number[]
  images: WebsiteImage[]
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
    <fieldset className="image-choice">
      <legend>{t('Bilder (optional)')}</legend>
      <p className="muted small">
        {t(
          'Bis zu {n} Bilder, z. B. Plakate aus mehreren Jahren. Die Webseite zeigt sie klein nebeneinander; groß lässt sich durch sie blättern.',
          { n: MAX_IMAGES },
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
          title={t('Bilder (optional)')}
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
    </fieldset>
  )
}
