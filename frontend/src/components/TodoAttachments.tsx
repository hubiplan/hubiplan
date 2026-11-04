import { useState } from 'react'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import { errorMessage, useLoad } from './forms.ts'
import { confirmLeave } from './leaveGuard.ts'
import { LoadError, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { followingChoice } from './TodoSeries.tsx'

interface Attachment {
  id: number
  kind?: 'file' | 'document'
  name: string
  size: number | null
  available: boolean
  deleted_at: string | null
}

export function TodoAttachments({
  base,
  id,
  writable,
  onSaved,
  recurring = false,
}: {
  base: string
  id: number
  writable: boolean
  onSaved: () => void
  recurring?: boolean
}) {
  const endpoint = `${base}${id}/attachments/`
  const { data, error, reload } = useLoad(
    () => api.get<{ items: Attachment[]; documents: { id: number; title: string }[] }>(endpoint),
    [endpoint],
  )
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [document, setDocument] = useState('')

  async function mutate(action: (version: number) => Promise<unknown>) {
    if (busy || !(await confirmLeave())) return
    setBusy(true)
    setActionError(null)
    try {
      const task = await todoApi.get(base, id)
      await action(task.version)
      await reload()
      onSaved()
    } catch (err) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function upload(files: File[]) {
    if (!files.length || !writable) return
    void mutate(async (version) => {
      for (const file of files) {
        const body = new FormData()
        body.append('file', file)
        body.append('version', String(version))
        const result = await api.post<{ version: number }>(endpoint, body)
        version = result.version
      }
    })
  }

  function list(items: Attachment[]) {
    return (
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item.id}>
            {item.available && !item.deleted_at ? (
              <a href={`${endpoint}${item.id}/`}>{item.name}</a>
            ) : (
              <span>{item.name}</span>
            )}
            {item.size !== null && (
              <span className="muted"> · {Math.ceil(item.size / 1024)} KB</span>
            )}
            {writable && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() => {
                  void mutate(async (version) => {
                    const following =
                      recurring && item.kind === 'document' ? await followingChoice() : false
                    if (following === null) return
                    await api.patch(`${endpoint}${item.id}/`, {
                      version,
                      deleted: !item.deleted_at,
                      following,
                    })
                  })
                }}
              >
                {t(item.deleted_at ? 'Wiederherstellen' : 'Entfernen')}
              </button>
            )}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <details className="card">
      <summary>{t('Anhänge')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      {actionError && <p role="alert">{actionError}</p>}
      {data && list(data.items.filter((item) => !item.deleted_at))}
      {writable && (
        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            upload(Array.from(event.dataTransfer.files))
          }}
        >
          <label>
            {t('Dateien hochladen')}
            <input
              type="file"
              multiple
              disabled={busy}
              onChange={(event) => {
                upload(Array.from(event.target.files ?? []))
                event.target.value = ''
              }}
            />
          </label>
          <p className="muted">
            {t('Dateien hier ablegen oder auswählen. Höchstens 20 MB je Datei.')}
          </p>
          {!!data?.documents.length && (
            <>
              <SelectField
                label={t('Dokument verknüpfen')}
                value={document}
                disabled={busy}
                onChange={(event) => setDocument(event.target.value)}
              >
                <option value="">{t('Bitte wählen')}</option>
                {data.documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.title}
                  </option>
                ))}
              </SelectField>
              <button
                className="button button-ghost"
                disabled={busy || !document}
                onClick={() => {
                  void mutate(async (version) => {
                    const following = recurring ? await followingChoice() : false
                    if (following === null) return
                    await api.post(endpoint, { version, document: Number(document), following })
                    setDocument('')
                  })
                }}
              >
                {t('Verknüpfen')}
              </button>
            </>
          )}
        </div>
      )}
      {!!data?.items.some((item) => item.deleted_at) && (
        <details>
          <summary>{t('Anhang-Papierkorb')}</summary>
          <p className="muted">{t('Entfernte Anhänge bleiben 30 Tage wiederherstellbar.')}</p>
          {list(data.items.filter((item) => item.deleted_at))}
        </details>
      )}
    </details>
  )
}
