import { useState } from 'react'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

type Preview = {
  valid: boolean
  errors: string[]
  counts: { pieces: number; arrangements: number; parts: number }
  skipped: number
  digest?: string
  preview?: string
}

export function CatalogueImportPanel({ onSaved }: { onSaved: () => Promise<unknown> }) {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/catalogue-import/`
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [key, setKey] = useState(newRequestKey)
  useDraftGuard(!!file && !done)
  async function run(action: 'preview' | 'import') {
    if (!file) return
    setBusy(true)
    setError('')
    const data = new FormData()
    data.append('file', file)
    data.append('action', action)
    if (action === 'import') {
      data.append('digest', preview?.digest || '')
      data.append('preview', preview?.preview || '')
    }
    try {
      const result = await api.post<Preview>(url, data, action === 'import' ? key : undefined)
      setPreview(result)
      if (action === 'preview') setKey(newRequestKey())
      if (action === 'import') {
        setDone(true)
        await onSaved()
      }
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack music-record">
      <h2>{t('Notenkatalog importieren')}</h2>
      <p>
        {t(
          'UTF-8-CSV bis 2 MB und 1000 Zeilen. Gleiche Einträge werden übersprungen; abweichende Bestände werden nicht überschrieben.',
        )}
      </p>
      <a href={url} className="button button-ghost">
        {t('CSV-Vorlage herunterladen')}
      </a>
      <label>
        {t('CSV-Datei für den Notenkatalog')}
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={busy}
          onChange={(e) => {
            setFile(e.target.files?.[0] || null)
            setPreview(null)
            setDone(false)
            setError('')
            setKey(newRequestKey())
          }}
        />
      </label>
      {error && <Alert kind="error">{error}</Alert>}
      <button
        className="button button-ghost"
        disabled={!file || busy || done}
        onClick={() => void run('preview')}
      >
        {t('Importvorschau erstellen')}
      </button>
      {preview && (
        <>
          {!!preview.errors.length && (
            <Alert kind="error" as="div">
              <ul>
                {preview.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
          {preview.valid && (
            <dl className="music-summary">
              {[
                [t('Neue Stücke'), preview.counts.pieces],
                [t('Neue Arrangements'), preview.counts.arrangements],
                [t('Neue Stimmenbestände'), preview.counts.parts],
                [t('Unveränderte Zeilen'), preview.skipped],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {done ? (
            <Alert kind="success">{t('Notenkatalog wurde importiert.')}</Alert>
          ) : (
            preview.valid && (
              <button
                className="button button-primary"
                disabled={busy}
                onClick={() => void run('import')}
              >
                {t('Geprüften Notenkatalog importieren')}
              </button>
            )
          )}
        </>
      )}
    </section>
  )
}
