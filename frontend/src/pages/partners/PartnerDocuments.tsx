// Dokumente an der Partnerakte (Konzept geschaeftspartner.md, P5): Verträge, Angebote,
// Einwilligungen und Schriftverkehr.
import { useRef, useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { partnerApi } from '../../api/partners.ts'
import type { BusinessPartner, PartnerDocument } from '../../api/partners.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { formatDay } from '../../i18n/format.ts'

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? t('{x} MB', { x: (bytes / 1024 / 1024).toFixed(1).replace('.', ',') })
    : t('{x} KB', { x: Math.max(1, Math.round(bytes / 1024)) })
}

export function PartnerDocuments({
  partner,
  canEdit,
}: {
  partner: BusinessPartner
  canEdit: boolean
}) {
  const org = useActiveOrg()
  const loaded = useLoad(() => partnerApi.documents(org.id, partner.id), [org.id, partner.id])
  const [items, setItems] = useState<PartnerDocument[] | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const list = items ?? loaded.data ?? []
  if (loaded.error) return <Alert kind="error">{loaded.error}</Alert>

  const upload = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const saved = await partnerApi.uploadDocument(org.id, partner.id, file, title)
      setItems([saved, ...list])
      setFile(null)
      setTitle('')
      if (input.current) input.current.value = ''
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="subcard stack">
      <h4>{t('Dokumente')}</h4>
      {list.length === 0 && (
        <p className="muted small">
          {t('Noch keine Dokumente, etwa Verträge, Angebote oder Einwilligungen.')}
        </p>
      )}
      <ul className="item-list">
        {list.map((d) => (
          <li key={d.id} className="item-row">
            <div className="item-row-info">
              <strong>{d.title || d.name}</strong>
              <div className="muted small">
                {[
                  d.title ? d.name : '',
                  formatSize(d.size),
                  formatDay(d.uploaded_at),
                  d.uploaded_by,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={() =>
                  void partnerApi
                    .downloadDocument(d.url)
                    .then((blob) => saveBlob(blob, d.name))
                    .catch((err: unknown) => setError(errorMessage(err)))
                }
              >
                {t('Herunterladen')}
              </button>
              {canEdit && (
                <button
                  type="button"
                  className="button button-danger"
                  onClick={async () => {
                    if (!(await confirmDialog(t('Dokument „{name}“ entfernen?', { name: d.name }))))
                      return
                    try {
                      await partnerApi.removeDocument(org.id, partner.id, d.id)
                      setItems(list.filter((x) => x.id !== d.id))
                    } catch (err) {
                      setError(errorMessage(err))
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="stack">
          <input
            ref={input}
            type="file"
            aria-label={t('Datei')}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file && (
            <Field
              label={t('Bezeichnung (optional)')}
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
          )}
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={!file || busy}
              onClick={() => void upload()}
            >
              {t('Dokument hochladen')}
            </button>
          </div>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </section>
  )
}
