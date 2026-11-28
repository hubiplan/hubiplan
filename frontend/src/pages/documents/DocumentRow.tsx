import { NextcloudSave } from '../../components/NextcloudFiles.tsx'
import { useState } from 'react'
import { DocumentIcon } from './DocumentIcons.tsx'
import './documents.css'
import { MaterialReferences } from '../../components/MaterialReferences.tsx'
import { docApi, formatSize } from '../../api/documents.ts'
import type { DocBase, DocFolder, DocItem } from '../../api/documents.ts'
import { formatDate, useAutoSave, useForm } from '../../components/forms.ts'
import { Field, SaveStatus } from '../../components/ui.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { t } from '../../i18n/index.ts'
import { ACCEPT, MAX_BYTES, type FolderCtx } from './documentsHelpers.ts'

/** Titel, Datum und Bemerkung eines Dokuments; speichert automatisch. */
function DocumentMetaForm({
  doc,
  base,
  onDone,
}: {
  doc: DocItem
  base: DocBase
  onDone: () => void
}) {
  const form = useForm({ title: doc.title, date: doc.date ?? '', note: doc.note })
  const auto = useAutoSave(form, (changes) =>
    docApi.update(base, doc.id, {
      ...changes,
      ...('date' in changes ? { date: changes.date || null } : {}),
    }),
  )
  const v = form.values
  return (
    <form
      className="inline-form"
      onSubmit={(e) => {
        e.preventDefault()
        void auto.flush().then((ok) => {
          if (ok) onDone()
        })
      }}
    >
      <SaveStatus auto={auto} />
      <div className="grid-3">
        <Field
          label={t('Titel')}
          value={v.title}
          required
          maxLength={200}
          error={form.errors.title}
          onChange={(e) => form.set('title', e.target.value)}
        />
        <Field
          label={t('Datum')}
          type="date"
          value={v.date}
          error={form.errors.date}
          onChange={(e) => form.set('date', e.target.value)}
        />
        <Field
          label={t('Bemerkung')}
          value={v.note}
          maxLength={500}
          error={form.errors.note}
          onChange={(e) => form.set('note', e.target.value)}
        />
      </div>
      <div className="button-row">
        <button type="submit" className="button button-ghost">
          {t('Schließen')}
        </button>
      </div>
    </form>
  )
}

export function DocumentRow({
  doc,
  folder,
  ...ctx
}: FolderCtx & { doc: DocItem; folder: DocFolder }) {
  const { base, manage, busy, run, folders, setMessage } = ctx
  const [editing, setEditing] = useState(false)
  const [inputKey, setInputKey] = useState(0)
  const current = doc.current

  async function addVersion(file: File | undefined) {
    if (!file) return
    if (file.size > MAX_BYTES) {
      setMessage({ kind: 'error', text: t('Die Datei ist größer als 20 MB.') })
      return
    }
    await run(async () => {
      await docApi.addVersion(base, doc.id, file)
      setInputKey((k) => k + 1)
    }, t('Die neue Fassung wurde hochgeladen.'))
  }

  return (
    <li>
      <DocumentIcon name={current?.name} contentType={current?.content_type} />
      <div className="doc-main">
        <strong>{doc.title}</strong>
        <MaterialReferences kind="document" id={doc.id} sourceBase={base} />
        {doc.date && <span className="muted"> · {formatDate(doc.date)}</span>}
        {doc.note && <div className="muted small">{doc.note}</div>}
        {current && (
          <div className="muted small">
            {current.name} {t('· {x} · hochgeladen am', { x: formatSize(current.size) })}{' '}
            {formatDate(current.uploaded_at)}
            {current.uploaded_by && t(' von {uploaded_by}', { uploaded_by: current.uploaded_by })}
          </div>
        )}
        {doc.versions && doc.versions.length > 1 && (
          <details className="doc-versions">
            <summary className="small">
              {t('Ältere Fassungen ({n})', { n: doc.versions.length - 1 })}
            </summary>
            <ul>
              {doc.versions.slice(1).map((v) => (
                <li key={v.id} className="small">
                  <a href={v.url} target="_blank" rel="noreferrer">
                    {v.name}
                  </a>{' '}
                  <span className="muted">
                    · {formatSize(v.size)} · {formatDate(v.uploaded_at)}
                  </span>
                  {manage && (
                    <button
                      type="button"
                      className="button button-ghost"
                      disabled={busy}
                      onClick={async () => {
                        if (
                          await confirmDialog({
                            final: true,
                            title: t('Fassung „{name}“ löschen?', { name: v.name }),
                            confirmLabel: t('Löschen'),
                          })
                        )
                          await run(
                            () => docApi.removeVersion(v.url),
                            t('Die Fassung wurde gelöscht.'),
                          )
                      }}
                    >
                      {t('Löschen')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
        {editing && (
          <DocumentMetaForm
            doc={doc}
            base={base}
            onDone={() => {
              setEditing(false)
              void run(async () => {})
            }}
          />
        )}
      </div>
      <div className="button-row">
        {current?.scan === 'pending' && (
          <span className="badge">{t('Wird auf Viren geprüft')}</span>
        )}
        {current?.scan === 'infected' && (
          <span className="badge">{t('Gesperrt: Schadsoftware gefunden')}</span>
        )}
        {current && !current.scan && (
          <a
            className="button button-ghost"
            href={current.inline ? current.url : `${current.url}?download=1`}
            target={current.inline ? '_blank' : undefined}
            rel="noreferrer"
          >
            {current.inline ? t('Ansehen') : t('Herunterladen')}
          </a>
        )}
        {current && !current.scan && (
          <NextcloudSave
            source={`${current.url}?download=1`}
            filename={current.name}
            category="records"
          />
        )}
        {manage && (
          <>
            <label className="button button-ghost doc-file-button">
              {t('Neue Fassung')}
              <input
                key={inputKey}
                disabled={busy}
                type="file"
                accept={ACCEPT}
                className="file-input"
                aria-label={t('Neue Fassung von {title}', { title: doc.title })}
                onChange={(e) => void addVersion(e.target.files?.[0])}
              />
            </label>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              {t('Bearbeiten')}
            </button>
            {folders.length > 1 && (
              <select
                aria-label={t('{title} verschieben', { title: doc.title })}
                className="doc-move"
                value=""
                disabled={busy}
                onChange={(e) =>
                  e.target.value &&
                  void run(
                    () => docApi.update(base, doc.id, { folder: Number(e.target.value) }),
                    t('Das Dokument wurde verschoben.'),
                  )
                }
              >
                <option value="">{t('Verschieben …')}</option>
                {folders
                  .filter((f) => f.id !== folder.id)
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {t('nach „{name}“', { name: f.name })}
                    </option>
                  ))}
              </select>
            )}
            <button
              type="button"
              className="button button-danger"
              disabled={busy}
              onClick={async () => {
                if (
                  await confirmDialog({
                    final: false,
                    title: t('„{title}“ löschen?', { title: doc.title }),
                    message: t('Das Dokument kommt in den Papierkorb und bleibt dort 30 Tage.'),
                    confirmLabel: t('In den Papierkorb'),
                  })
                )
                  await run(
                    () => docApi.trashDocument(base, doc.id),
                    t('Das Dokument liegt jetzt im Papierkorb.'),
                  )
              }}
            >
              {t('Löschen')}
            </button>
          </>
        )}
      </div>
    </li>
  )
}
