import { NextcloudPick } from '../../components/NextcloudFiles.tsx'
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import type { Booking, Receipt } from '../../api/finance.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { ApiError } from '../../api/client.ts'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'

/** Vor weniger als 15 Minuten hochgeladen: darf noch gelöscht werden (sonst ausblenden). */
function justUploaded(createdAt: string): boolean {
  return Date.now() - Date.parse(createdAt) < 15 * 60 * 1000
}

export function Receipts({
  orgId,
  booking,
  canEdit,
}: {
  orgId: number
  booking: Booking
  canEdit: boolean
}) {
  const [items, setItems] = useState(booking.receipts)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(files: FileList | File[] | null) {
    if (!files?.length) return
    setBusy(true)
    setError(null)
    // Jede Datei einzeln: Gespeichertes sofort zeigen, Fehler je Datei nennen
    const list = Array.from(files)
    const failed: string[] = []
    let done = 0
    for (const file of list) {
      try {
        const receipt = await financeApi.uploadReceipt(orgId, booking.id, file)
        setItems((prev) => [...prev, receipt])
        done++
      } catch (err) {
        failed.push(t('{name}: {x}', { name: file.name, x: errorMessage(err) }))
      }
    }
    if (failed.length) {
      setError(
        (list.length > 1
          ? t('{done} von {n} Belegen hochgeladen. ', { done, n: list.length })
          : '') + t('Nicht hochgeladen – bitte erneut auswählen: {x}', { x: failed.join('; ') }),
      )
    }
    setBusy(false)
  }

  async function hide(id: number) {
    const reason = await promptDialog({
      title: t('Beleg ausblenden?'),
      message:
        t(
          'Belege werden aufbewahrt (§ 147 AO) und nicht gelöscht. Der Beleg verschwindet aus der ',
        ) + t('Liste „mit Beleg“, bleibt aber gespeichert und steht im Datenexport.'),
      label: t('Grund'),
      confirmLabel: t('Ausblenden'),
    })
    if (reason === null) return
    try {
      const hidden = (await financeApi.deleteReceipt(orgId, id, reason)) as Receipt
      setItems((prev) => prev.map((r) => (r.id === id ? hidden : r)))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function remove(r: Receipt) {
    setError(null)
    // Gerade hochgeladen: löschen (Fehlgriff); sonst nur ausblenden
    const recent = justUploaded(r.created_at) && !booking.fixed
    if (!recent) return hide(r.id)
    if (
      !(await confirmDialog({
        final: true,
        title: t('Beleg entfernen?'),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    try {
      await financeApi.deleteReceipt(orgId, r.id)
      setItems((prev) => prev.filter((x) => x.id !== r.id))
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) return hide(r.id)
      setError(errorMessage(err))
    }
  }

  return (
    <div className="subcard">
      <h3>{t('Belege')}</h3>
      <Why k="receipts" />
      {items.length === 0 ? (
        <p className="muted small">{t('Noch kein Beleg.')}</p>
      ) : (
        <ul className="plain-list">
          {items.map((r) => (
            <li key={r.id} className={r.hidden_at ? 'muted' : undefined}>
              <a href={financeApi.receiptUrl(orgId, r.id)} target="_blank" rel="noreferrer">
                📎 {r.name}
              </a>{' '}
              <span className="muted small">({Math.ceil(r.size / 1024)} KB)</span>
              {r.einvoice?.number && (
                <span className="small">
                  {' '}
                  {t('· E-Rechnung')} {r.einvoice.number}
                  {r.einvoice.seller ? t(' von {seller}', { seller: r.einvoice.seller }) : ''}
                  {r.einvoice.payable ? t(' über {x}', { x: euro(r.einvoice.payable) }) : ''}
                  {r.content_type === 'application/xml' && (
                    <>
                      {' '}
                      <a
                        href={financeApi.receiptViewUrl(orgId, r.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {t('lesbare Ansicht')}
                      </a>
                    </>
                  )}
                </span>
              )}
              {r.hidden_at ? (
                <span className="small">
                  {' '}
                  {t('– ausgeblendet:')} {r.hidden_reason}
                </span>
              ) : (
                canEdit && (
                  <button type="button" className="link-button" onClick={() => void remove(r)}>
                    {t('entfernen')}
                  </button>
                )
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <label className="button button-ghost file-button">
          {busy ? t('Lädt hoch …') : t('Foto, PDF oder E-Rechnung hinzufügen')}
          <input
            type="file"
            accept="application/pdf,image/*,.xml,application/xml,text/xml"
            multiple
            className="file-input"
            disabled={busy}
            onChange={(e) => {
              void upload(e.target.files)
              e.target.value = ''
            }}
          />
        </label>
      )}
      {canEdit && !busy && (
        <NextcloudPick
          accept={['.pdf', 'image/', '.xml']}
          multiple
          onFile={(file) => upload([file])}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
