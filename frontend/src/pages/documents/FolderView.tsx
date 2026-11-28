import { NextcloudPick } from '../../components/NextcloudFiles.tsx'
import { useState } from 'react'
import { FolderIcon } from './DocumentIcons.tsx'
import './documents.css'
import type { FormEvent } from 'react'
import { docApi } from '../../api/documents.ts'
import type { DocFolder, DocItem, Visibility } from '../../api/documents.ts'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { RightsHint } from '../../components/RightsHint.tsx'
import { t, tn } from '../../i18n/index.ts'
import { ACCEPT, MAX_BYTES, type FolderCtx } from './documentsHelpers.ts'
import { DocumentRow } from './DocumentRow.tsx'

export function FolderView({
  folder,
  docs,
  from,
  ...ctx
}: FolderCtx & { folder: DocFolder; docs: DocItem[]; from?: string }) {
  const { base, manage, busy, run, visibilities, setMessage, shareUp } = ctx
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const [note, setNote] = useState('')
  const [inputKey, setInputKey] = useState(0)

  async function upload(e: FormEvent) {
    e.preventDefault()
    if (!file) return
    if (file.size > MAX_BYTES) {
      setMessage({ kind: 'error', text: t('Die Datei ist größer als 20 MB.') })
      return
    }
    await run(async () => {
      await docApi.upload(base, folder.id, file, {
        title: title.trim() || file.name.replace(/\.[^.]+$/, ''),
        date,
        note,
      })
      setFile(null)
      setTitle('')
      setDate('')
      setNote('')
      setInputKey((k) => k + 1)
    }, t('Das Dokument wurde hochgeladen.'))
  }

  async function rename() {
    const name = await promptDialog({
      title: t('Ordner umbenennen'),
      label: t('Name'),
      defaultValue: folder.name,
      confirmLabel: t('Umbenennen'),
      danger: false,
    })
    if (name && name.trim() && name.trim() !== folder.name) {
      await run(() => docApi.updateFolder(base, folder.id, { name: name.trim() }))
    }
  }

  async function remove() {
    if (folder.documents.length > 0) {
      setMessage({
        kind: 'error',
        text: t('Der Ordner ist nicht leer. Bitte zuerst die Dokumente verschieben oder löschen.'),
      })
      return
    }
    if (
      await confirmDialog({
        final: false,
        title: t('Ordner „{name}“ löschen?', { name: folder.name }),
        confirmLabel: t('Löschen'),
      })
    )
      await run(() => docApi.deleteFolder(base, folder.id), t('Der Ordner wurde gelöscht.'))
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setMessage({ kind: 'success', text: t('Link kopiert.') })
    } catch {
      setMessage({ kind: 'error', text: t('Kopieren ging nicht. Bitte den Link markieren.') })
    }
  }

  return (
    <section className="doc-folder" aria-label={folder.name}>
      <div className="doc-folder-heading">
        <FolderIcon locked={folder.visibility === 'board'} />
        <h2>{folder.name}</h2>
        {folder.department && <span className="badge">{folder.department}</span>}
        <span className="badge">{from ? t('von {from}', { from }) : folder.visibility_label}</span>
        {!from && folder.shared_up && <span className="badge">{t('nach oben freigegeben')}</span>}
        <span className="muted small">
          {' '}
          {tn('· {n} Dokument', '· {n} Dokumente', folder.documents.length)}
        </span>
        {!manage && <span className="badge">{t('Nur lesen')}</span>}
      </div>
      {manage && (
        <div className="doc-folder-tools">
          <SelectField
            label={t('Sichtbar für')}
            value={folder.visibility}
            disabled={busy}
            onChange={(e) =>
              void run(() =>
                docApi.updateFolder(base, folder.id, { visibility: e.target.value as Visibility }),
              )
            }
          >
            {visibilities.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </SelectField>
          {shareUp && (
            <Checkbox
              label={shareUp}
              checked={folder.shared_up}
              disabled={busy}
              onChange={(on) =>
                void run(() => docApi.updateFolder(base, folder.id, { shared_up: on }))
              }
            />
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void rename()}
            >
              {t('Umbenennen')}
            </button>
            <button
              type="button"
              className="button button-danger"
              disabled={busy}
              onClick={() => void remove()}
            >
              {t('Ordner löschen')}
            </button>
          </div>
          {folder.public_url && (
            <p className="statute-link small">
              {t('Öffentlicher Link (Liste als JSON, z. B. für die Webseite):')}{' '}
              <code>{folder.public_url}</code>{' '}
              <button
                type="button"
                className="button button-ghost"
                onClick={() => void copy(folder.public_url!)}
              >
                {t('Link kopieren')}
              </button>
            </p>
          )}
        </div>
      )}
      {docs.length === 0 ? (
        <p className="muted small">{t('Keine Dokumente in diesem Ordner.')}</p>
      ) : (
        <ul className="statute-list doc-list">
          {docs.map((d) => (
            <DocumentRow key={d.id} doc={d} folder={folder} {...ctx} manage={manage} />
          ))}
        </ul>
      )}
      {manage && (
        <form onSubmit={upload} className="inline-form">
          <div className="grid-3">
            <label className="field">
              <span>{t('Datei (höchstens 20 MB)')}</span>
              <input
                key={inputKey}
                disabled={busy}
                type="file"
                accept={ACCEPT}
                aria-label={t('Datei für {name}', { name: folder.name })}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <NextcloudPick
                accept={[
                  '.pdf',
                  '.doc',
                  '.docx',
                  '.xls',
                  '.xlsx',
                  '.ppt',
                  '.pptx',
                  '.odt',
                  '.ods',
                  '.odp',
                  '.jpg',
                  '.jpeg',
                  '.png',
                  '.txt',
                  '.csv',
                ]}
                onFile={(f) => {
                  setFile(f)
                  if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''))
                }}
              />
              {file && <span className="muted small">{file.name}</span>}
              <RightsHint />
            </label>
            <Field
              label={t('Titel')}
              value={title}
              maxLength={200}
              placeholder={file ? file.name.replace(/\.[^.]+$/, '') : ''}
              onChange={(e) => setTitle(e.target.value)}
            />
            <Field
              label={t('Datum')}
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <Field
            label={t('Bemerkung (optional)')}
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
          />
          <button type="submit" className="button button-primary" disabled={busy || !file}>
            {t('Hochladen')}
          </button>
        </form>
      )}
    </section>
  )
}
