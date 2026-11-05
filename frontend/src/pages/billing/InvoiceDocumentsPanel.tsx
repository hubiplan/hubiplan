import { useState } from 'react'
import { einvoiceApi } from '../../api/einvoices.ts'
import type { CommercialInvoice } from '../../api/einvoices.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

const statuses: Record<string, () => string> = {
  prepared: () => t('Vorbereitet'),
  dispatching: () => t('Übermittlung läuft'),
  unknown: () => t('Übermittlung unbestätigt'),
  submitted: () => t('Beim Anbieter eingereicht'),
  delivered: () => t('Zugestellt'),
  rejected: () => t('Vom Anbieter abgelehnt'),
}

export function InvoiceDocumentsPanel({
  org,
  invoice,
  canEdit,
  reload,
}: {
  org: number
  invoice: CommercialInvoice
  canEdit: boolean
  reload: () => Promise<unknown>
}) {
  const load = useLoad(() => einvoiceApi.delivery(org, invoice.id), [org, invoice.id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function act(operation: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await operation()
      await reload()
      await load.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const documents =
    invoice.status === 'cancelled' ? (['invoice', 'cancellation'] as const) : (['invoice'] as const)
  return (
    <section className="subcard stack">
      <h3>{t('ZUGFeRD und elektronische Übermittlung')}</h3>
      <p className="muted">
        {t(
          'ZUGFeRD enthält eine lesbare PDF/A-Datei und das geprüfte Rechnungs-XML. Originale bleiben unverändert.',
        )}
      </p>
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      {documents.map((document) => {
        const cancel = document === 'cancellation'
        const exists = cancel ? invoice.has_cancellation_hybrid : invoice.has_hybrid
        const delivery = load.data?.deliveries.find((row) => row.document === document)
        const terminal =
          delivery && ['submitted', 'delivered', 'rejected'].includes(delivery.status)
        return (
          <div className="stack" key={document}>
            <h4>{cancel ? t('Stornorechnung') : t('Rechnungsoriginal')}</h4>
            <div className="actions">
              {exists ? (
                <a
                  className="button button-ghost"
                  href={einvoiceApi.hybrid(org, invoice.id, cancel)}
                >
                  {t('ZUGFeRD herunterladen')}
                </a>
              ) : (
                canEdit && (
                  <button
                    className="button button-ghost"
                    disabled={busy}
                    onClick={() =>
                      void act(() => einvoiceApi.createHybrid(org, invoice.id, cancel))
                    }
                  >
                    {t('ZUGFeRD erstellen und prüfen')}
                  </button>
                )
              )}
              {load.data?.configuration.enabled && canEdit && (
                <>
                  {(cancel || invoice.status !== 'cancelled') && !terminal && (
                    <button
                      className="button button-primary"
                      disabled={busy || delivery?.status === 'dispatching'}
                      onClick={() =>
                        void act(() => einvoiceApi.dispatch(org, invoice.id, document, 'send'))
                      }
                    >
                      {delivery
                        ? t('Übermittlung erneut abgleichen')
                        : t('Elektronisch übermitteln')}
                    </button>
                  )}
                  {delivery && (
                    <button
                      className="button button-ghost"
                      disabled={busy}
                      onClick={() =>
                        void act(() => einvoiceApi.dispatch(org, invoice.id, document, 'refresh'))
                      }
                    >
                      {t('Versandstatus abrufen')}
                    </button>
                  )}
                </>
              )}
            </div>
            {delivery && (
              <p>
                {statuses[delivery.status]?.() ?? delivery.status} · {delivery.provider}
                {delivery.receipt.reference && <> · {delivery.receipt.reference}</>}
              </p>
            )}
            {delivery?.status === 'unknown' && (
              <Alert kind="info">
                {t(
                  'Die Zustellung ist noch nicht bestätigt. Vor einem erneuten Versand wird die bestehende Übermittlung beim Anbieter abgeglichen.',
                )}
              </Alert>
            )}
          </div>
        )
      })}
      {load.data && (
        <p className="muted small">
          {load.data.configuration.enabled
            ? `${load.data.configuration.label} · ${load.data.configuration.participant}`
            : t(
                'Eine Versandanbindung kann die Plattformverwaltung für diesen Verein einrichten. Bis dahin können Rechnungen heruntergeladen und im Empfängerportal hochgeladen werden.',
              )}
        </p>
      )}
    </section>
  )
}
