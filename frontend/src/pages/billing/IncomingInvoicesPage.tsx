import { useState } from 'react'
import { Link } from 'react-router-dom'
import { einvoiceApi } from '../../api/einvoices.ts'
import type { IncomingInvoice } from '../../api/einvoices.ts'
import { financeApi } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ValidationResult } from './EInvoicesPage.tsx'

export function IncomingInvoicesPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [page, setPage] = useState(1)
  const load = useLoad(() => einvoiceApi.incoming(org.id, page), [org.id, page])
  const [selected, setSelected] = useState<IncomingInvoice | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const changed = (item: IncomingInvoice) => {
    setSelected(item)
    void load.reload()
  }
  return (
    <div className="stack">
      <p>
        {t(
          'XML- und ZUGFeRD-Rechnungen werden im Original gespeichert. Ein Import erzeugt keine Buchung und keine Zahlung.',
        )}
      </p>
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      {canEdit && (
        <Field
          label={t('E-Rechnung importieren')}
          type="file"
          accept=".xml,.pdf,application/xml,application/pdf"
          disabled={busy}
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return
            setBusy(true)
            setError('')
            try {
              changed(await einvoiceApi.upload(org.id, file))
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
              e.target.value = ''
            }
          }}
        />
      )}
      {busy && <p role="status">{t('Die Datei wird geprüft …')}</p>}
      {selected && (
        <IncomingDetail
          key={selected.id}
          value={selected}
          canEdit={canEdit}
          onChanged={changed}
          onClose={() => setSelected(null)}
        />
      )}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('Rechnung')}</th>
              <th>{t('Rechnungssteller')}</th>
              <th>{t('Betrag')}</th>
              <th>{t('Status')}</th>
            </tr>
          </thead>
          <tbody>
            {load.data?.results.map((item) => (
              <tr key={item.id}>
                <td>
                  <button className="button button-ghost" onClick={() => setSelected(item)}>
                    {item.data.number || item.name}
                  </button>
                </td>
                <td>{item.data.seller || '—'}</td>
                <td>
                  {item.data.payable} {item.data.currency}
                </td>
                <td>
                  {item.booking
                    ? t('Zugeordnet')
                    : item.status === 'approved'
                      ? t('Freigegeben')
                      : item.status === 'rejected'
                        ? t('Abgelehnt')
                        : t('Zu prüfen')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {load.data?.count === 0 && <p>{t('Noch keine Eingangsrechnungen vorhanden.')}</p>}
      </div>
      <div className="actions">
        <button
          className="button button-ghost"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          {t('Zurück')}
        </button>
        <button
          className="button button-ghost"
          disabled={!load.data?.next}
          onClick={() => setPage(page + 1)}
        >
          {t('Weiter')}
        </button>
      </div>
    </div>
  )
}

function IncomingDetail({
  value,
  canEdit,
  onChanged,
  onClose,
}: {
  value: IncomingInvoice
  canEdit: boolean
  onChanged: (value: IncomingInvoice) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const canLink = canEdit && value.status === 'approved' && !value.booking
  const bookings = useLoad(
    () =>
      canLink
        ? financeApi.bookings(org.id, {
            suche: search,
            page,
            art: value.data.credit_note ? 'income' : 'expense',
          })
        : Promise.resolve(null),
    [org.id, search, page, canLink, value.data.credit_note],
  )
  const [note, setNote] = useState(value.review_note)
  const [booking, setBooking] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function act(action: () => Promise<IncomingInvoice>) {
    setBusy(true)
    setError('')
    try {
      onChanged(await action())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card stack">
      <div className="page-head">
        <h2>{value.data.number || value.name}</h2>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <ValidationResult report={value.report} />
      <dl className="facts">
        <dt>{t('Rechnungssteller')}</dt>
        <dd>{value.data.seller || '—'}</dd>
        <dt>{t('Empfänger')}</dt>
        <dd>{value.data.buyer || '—'}</dd>
        <dt>{t('Betrag')}</dt>
        <dd>
          {value.data.payable} {value.data.currency}
        </dd>
        <dt>{t('IBAN')}</dt>
        <dd>{value.data.iban || '—'}</dd>
      </dl>
      <div className="actions">
        <a className="button button-ghost" href={einvoiceApi.download(org.id, value.id)}>
          {t('Original herunterladen')}
        </a>
        {value.data.number && (
          <a className="button button-ghost" href={einvoiceApi.download(org.id, value.id, 'view')}>
            {t('Lesbare Ansicht')}
          </a>
        )}
        {value.has_report && (
          <a
            className="button button-ghost"
            href={einvoiceApi.download(org.id, value.id, 'report_xml')}
          >
            {t('Prüfbericht herunterladen')}
          </a>
        )}
      </div>
      {canEdit && !value.booking && (
        <>
          <p>
            {t(
              'Vor der Freigabe Empfänger, Leistung, Betrag und Bankverbindung anhand der Vereinbarung prüfen. Technische Gültigkeit bestätigt diese Angaben nicht.',
            )}
          </p>
          <Field
            label={t('Prüfvermerk')}
            value={note}
            disabled={busy}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="actions">
            <button
              className="button button-primary"
              disabled={busy || !note.trim() || value.report.status !== 'valid'}
              onClick={() => void act(() => einvoiceApi.review(org.id, value.id, 'approved', note))}
            >
              {t('Fachlich freigeben')}
            </button>
            <button
              className="button button-ghost"
              disabled={busy || !note.trim()}
              onClick={() => void act(() => einvoiceApi.review(org.id, value.id, 'rejected', note))}
            >
              {t('Ablehnen')}
            </button>
            {value.status === 'review' && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() => void act(() => einvoiceApi.revalidate(org.id, value.id))}
              >
                {t('Erneut prüfen')}
              </button>
            )}
          </div>
        </>
      )}
      {value.status === 'approved' && !value.booking && canEdit && (
        <div className="subcard stack">
          <p>
            {t(
              'Nach erfolgter Zahlung die passende Kassenbuchung zuordnen. Teilzahlungen werden hier noch nicht zugeordnet.',
            )}
          </p>
          {bookings.error && <Alert kind="error">{bookings.error}</Alert>}
          <Field
            label={t('Buchungen suchen')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
              setBooking('')
            }}
          />
          <SelectField
            label={t('Kassenbuchung')}
            value={booking}
            onChange={(e) => setBooking(e.target.value)}
            disabled={busy}
          >
            <option value="">{t('Bitte wählen')}</option>
            {bookings.data?.results
              .filter(
                (item) =>
                  Number(item.amount) === Number(value.data.payable) &&
                  !item.cancels &&
                  !item.cancelled_by,
              )
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.number} · {item.date} · {item.text}
                </option>
              ))}
          </SelectField>
          <div className="actions">
            <button
              className="button button-ghost"
              disabled={page <= 1 || busy}
              onClick={() => {
                setPage(page - 1)
                setBooking('')
              }}
            >
              {t('Vorherige Buchungen')}
            </button>
            <button
              className="button button-ghost"
              disabled={!bookings.data?.next || busy}
              onClick={() => {
                setPage(page + 1)
                setBooking('')
              }}
            >
              {t('Weitere Buchungen')}
            </button>
          </div>
          <div className="actions">
            <button
              className="button button-primary"
              disabled={busy || !booking}
              onClick={() => void act(() => einvoiceApi.link(org.id, value.id, Number(booking)))}
            >
              {t('Buchung zuordnen')}
            </button>
            <Link className="button button-ghost" to="/finanzen/kassenbuch">
              {t('Zum Kassenbuch')}
            </Link>
          </div>
        </div>
      )}
      {value.booking && (
        <Link to={`/finanzen/kassenbuch?buchung=${value.booking}`}>
          {t('Zugeordnete Buchung öffnen')}
        </Link>
      )}
    </div>
  )
}
