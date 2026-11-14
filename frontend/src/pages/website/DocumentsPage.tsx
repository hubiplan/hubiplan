// Dokumente der Webseite (Ralf 05.11.2026): Pressespiegel und eigene Dokumente als PDF oder
// Bild. Der Pressespiegel erscheint im Bereich „Presse“, eigene Dokumente unter „Dokumente“
// neben Satzung und Beitragsordnung.
import { useState } from 'react'
import { documentApi } from '../../api/website.ts'
import type { DocumentSection, WebsiteDocument } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

const ACCEPT = 'application/pdf,image/jpeg,image/png,image/webp'

function sectionLabel(section: DocumentSection) {
  return section === 'press' ? t('Presse') : t('Dokumente')
}

export function DocumentsPage() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => documentApi.list(org.id), [org.id])
  const [section, setSection] = useState<DocumentSection>('press')
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [date, setDate] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [fileKey, setFileKey] = useState(0)

  async function upload() {
    if (!file) return
    setBusy(true)
    setMessage(null)
    try {
      await documentApi.upload(org.id, file, {
        section,
        title: title.trim() || file.name.replace(/\.[^.]+$/, ''),
        source: source.trim(),
        date: date || null,
      })
      setTitle('')
      setSource('')
      setDate('')
      setFile(null)
      setFileKey((k) => k + 1)
      await reload()
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Zeitungsartikel und andere Dateien als PDF oder Bild. Der Pressespiegel erscheint im Bereich „Presse“, eigene Dokumente unter „Dokumente“ neben Satzung und Beitragsordnung. Beide Bereiche schaltest du unter „Menü und Bausteine“ ein.',
        )}
      </p>
      <section className="card stack">
        <h2>{t('Dokument hochladen')}</h2>
        <div className="grid-2">
          <SelectField
            label={t('Bereich')}
            value={section}
            onChange={(e) => setSection(e.target.value as DocumentSection)}
          >
            <option value="press">{t('Presse')}</option>
            <option value="documents">{t('Dokumente')}</option>
          </SelectField>
          <Field
            label={t('Datei (PDF oder Bild)')}
            type="file"
            accept={ACCEPT}
            key={fileKey}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Field
            label={t('Titel')}
            value={title}
            maxLength={200}
            hint={t('leer: Dateiname')}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Field
            label={t('Quelle')}
            value={source}
            maxLength={200}
            hint={t('z. B. Name der Zeitung')}
            onChange={(e) => setSource(e.target.value)}
          />
          <Field
            label={t('Datum')}
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        {message && <Alert kind="error">{message}</Alert>}
        <div className="actions">
          <button
            type="button"
            className="button button-primary"
            disabled={!file || busy}
            onClick={() => void upload()}
          >
            {busy ? t('Wird hochgeladen …') : t('Hochladen')}
          </button>
        </div>
      </section>
      {(['press', 'documents'] as DocumentSection[]).map((s) => {
        const rows = data.filter((d) => d.section === s)
        return (
          <section key={s} className="stack">
            <h2>{sectionLabel(s)}</h2>
            {rows.length === 0 && <p className="muted">{t('Noch keine Einträge vorhanden.')}</p>}
            {rows.map((d) => (
              <DocumentRow key={d.id} doc={d} onChanged={() => void reload()} />
            ))}
          </section>
        )
      })}
    </div>
  )
}

function DocumentRow({ doc, onChanged }: { doc: WebsiteDocument; onChanged: () => void }) {
  const org = useActiveOrg()
  const [title, setTitle] = useState(doc.title)
  const [source, setSource] = useState(doc.source)
  const [date, setDate] = useState(doc.date ?? '')
  const [message, setMessage] = useState<string | null>(null)
  const changed = title !== doc.title || source !== doc.source || date !== (doc.date ?? '')

  async function save(data: Parameters<typeof documentApi.save>[2]) {
    setMessage(null)
    try {
      await documentApi.save(org.id, doc.id, data)
      onChanged()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Dokument löschen?'),
      message: t('„{x}“ verschwindet von der Webseite und aus HUBIplan.', { x: doc.title }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await documentApi.remove(org.id, doc.id)
      onChanged()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <article className="card document-row">
      <a href={doc.url} target="_blank" rel="noopener noreferrer" className="document-preview">
        {doc.preview_url ? (
          <img src={doc.preview_url} alt="" loading="lazy" />
        ) : (
          <span aria-hidden="true">PDF</span>
        )}
        <span className="sr-only">{t('{x} öffnen', { x: doc.title })}</span>
      </a>
      <div className="stack">
        <div className="grid-2">
          <Field
            label={t('Titel')}
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Field
            label={t('Quelle')}
            value={source}
            maxLength={200}
            onChange={(e) => setSource(e.target.value)}
          />
          <Field
            label={t('Datum')}
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
          <SelectField
            label={t('Bereich')}
            value={doc.section}
            onChange={(e) => void save({ section: e.target.value as DocumentSection })}
          >
            <option value="press">{t('Presse')}</option>
            <option value="documents">{t('Dokumente')}</option>
          </SelectField>
        </div>
        <Checkbox
          label={t('Auf der Webseite zeigen')}
          checked={doc.published}
          onChange={(on) => void save({ published: on })}
        />
        {message && <Alert kind="error">{message}</Alert>}
        <div className="actions">
          {changed && (
            <button
              type="button"
              className="button button-primary"
              disabled={!title.trim()}
              onClick={() => void save({ title: title.trim(), source, date: date || null })}
            >
              {t('Speichern')}
            </button>
          )}
          <button type="button" className="button button-ghost" onClick={() => void remove()}>
            {t('Löschen')}
          </button>
        </div>
      </div>
    </article>
  )
}
