import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { einvoiceApi } from '../../api/einvoices.ts'
import type { IncomingInvoice, IncomingMail } from '../../api/einvoices.ts'
import { financeApi } from '../../api/finance.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { ValidationResult } from './EInvoicesPage.tsx'
import { PageNav } from '../../components/ListControls.tsx'

/** Abstand der Nachfragen, solange eine Prüfung läuft. */
const POLL_MS = 4000

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
  // Ist die Prüfung des geöffneten Eingangs inzwischen fertig, den neuen Stand zeigen
  const fresh = load.data?.results.find((item) => item.id === selected?.id)
  const shown =
    selected && fresh && selected.report.status === 'pending' && fresh.report.status !== 'pending'
      ? fresh
      : selected
  // Die technische Prüfung läuft im Hintergrund: solange etwas wartet, nachfragen
  const { reload } = load
  const waiting =
    shown?.report.status === 'pending' ||
    !!load.data?.results.some((item) => item.report.status === 'pending')
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => void reload(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [waiting, reload])
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
      {busy && <p role="status">{t('Die Datei wird hochgeladen …')}</p>}
      <MailboxCard canEdit={canEdit} />
      {shown && (
        <IncomingDetail
          key={shown.id}
          value={shown}
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
                <td>
                  {item.partner_name || item.data.seller || '—'}
                  {item.mail && !item.mail.sender_known && (
                    <>
                      {' '}
                      <span className="badge">{t('Absender unbekannt')}</span>
                    </>
                  )}
                  {item.iban_changed && !item.booking && (
                    <>
                      {' '}
                      <span className="badge">{t('Neue IBAN')}</span>
                    </>
                  )}
                </td>
                <td>
                  {item.data.payable} {item.data.currency}
                </td>
                <td>
                  {item.booking
                    ? t('Zugeordnet')
                    : item.report.status === 'pending'
                      ? t('Wird geprüft')
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
      <PageNav
        prevDisabled={page <= 1}
        nextDisabled={!load.data?.next}
        onPrev={() => setPage(page - 1)}
        onNext={() => setPage(page + 1)}
      />
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
  const [ibanConfirmed, setIbanConfirmed] = useState(false)
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
      <div className="card-head">
        <h2>{value.data.number || value.name}</h2>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <ValidationResult report={value.report} />
      {value.mail && !value.mail.sender_known && (
        <Alert kind="info">
          {t(
            'Der Absender der Mail passt zu keinem Geschäftspartner. Prüfe vor der Freigabe besonders Rechnungssteller und Bankverbindung.',
          )}
        </Alert>
      )}
      <dl className="facts">
        {value.mail && (
          <>
            <dt>{t('Per Mail von')}</dt>
            <dd>
              {value.mail.sender || '—'} · {formatDateTime(value.mail.received_at)}
            </dd>
          </>
        )}
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
        <dt>{t('Geschäftspartner')}</dt>
        <dd>{value.partner_name || '—'}</dd>
      </dl>
      <PartnerChoice value={value} canEdit={canEdit} busy={busy} act={act} />
      {value.iban_changed && !value.booking && (
        <Alert kind="error">
          {t(
            'Neue Bankverbindung: Die IBAN der Rechnung weicht von der beim Geschäftspartner gespeicherten ab. Bitte beim Rechnungssteller telefonisch bestätigen, bevor du freigibst.',
          )}
        </Alert>
      )}
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
          <Why k="incoming_approval" />
          <Field
            label={t('Prüfvermerk')}
            value={note}
            disabled={busy}
            onChange={(e) => setNote(e.target.value)}
          />
          {value.iban_changed && value.status === 'review' && (
            <Checkbox
              label={t('Neue IBAN telefonisch bestätigt')}
              checked={ibanConfirmed}
              disabled={busy}
              onChange={setIbanConfirmed}
            />
          )}
          <div className="actions">
            <button
              className="button button-primary"
              disabled={
                busy ||
                !note.trim() ||
                value.report.status !== 'valid' ||
                (!!value.iban_changed && !ibanConfirmed)
              }
              onClick={() =>
                void act(() =>
                  einvoiceApi.review(org.id, value.id, 'approved', note, ibanConfirmed),
                )
              }
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
            {value.status === 'review' && value.report.status !== 'pending' && (
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

/** Woran HUBIplan den vorgeschlagenen Geschäftspartner erkannt hat. */
function suggestedBy(by: string): string {
  switch (by) {
    case 'vat_id':
      return t('an der USt-IdNr.')
    case 'iban':
      return t('an der IBAN')
    case 'sender':
      return t('am Absender der Mail')
    case 'domain':
      return t('an der Domain des Absenders')
    default:
      return t('am Namen')
  }
}

/** Geschäftspartner zuordnen: Vorschlag übernehmen, neu anlegen oder lösen (P3). */
function PartnerChoice({
  value,
  canEdit,
  busy,
  act,
}: {
  value: IncomingInvoice
  canEdit: boolean
  busy: boolean
  act: (action: () => Promise<IncomingInvoice>) => Promise<void>
}) {
  const org = useActiveOrg()
  const suggestion = value.suggested_partner
  if (value.partner) {
    if (!canEdit) return null
    return (
      <div className="actions">
        <button
          className="button button-ghost"
          disabled={busy}
          onClick={() => void act(() => einvoiceApi.assignPartner(org.id, value.id, null))}
        >
          {t('Zuordnung zum Geschäftspartner lösen')}
        </button>
      </div>
    )
  }
  return (
    <div className="subcard stack">
      {suggestion ? (
        <p>
          {t('Vorschlag: {name} (erkannt {by})', {
            name: suggestion.name,
            by: suggestedBy(suggestion.by),
          })}
        </p>
      ) : (
        <p>{t('Kein passender Geschäftspartner gefunden.')}</p>
      )}
      {canEdit && (
        <div className="actions">
          {suggestion && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                void act(() => einvoiceApi.assignPartner(org.id, value.id, suggestion.id))
              }
            >
              {t('Vorschlag zuordnen')}
            </button>
          )}
          {value.data.seller && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => void act(() => einvoiceApi.createPartner(org.id, value.id))}
            >
              {t('Als Geschäftspartner anlegen')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** Grund, warum ein Anhang nicht übernommen wurde. */
function reasonText(reason: string): string {
  switch (reason) {
    case 'plain_pdf':
      return t('PDF ohne E-Rechnung')
    case 'too_big':
      return t('größer als 15 MB')
    case 'too_many':
      return t('zu viele Rechnungen in einer Mail')
    case 'virus':
      return t('Schadsoftware gefunden')
    case 'mail_too_big':
      return t('Mail größer als 25 MB')
    case 'error':
      return t('nicht verarbeitet')
    default:
      return t('keine E-Rechnung')
  }
}

function mailStatusText(mail: IncomingMail): string {
  switch (mail.status) {
    case 'imported':
      return t('Übernommen, aber nicht alle Anhänge')
    case 'spam':
      return t('Vom Spamfilter markiert, nicht übernommen')
    case 'virus':
      return t('Schadsoftware gefunden, nicht übernommen')
    case 'error':
      return t('Nicht verarbeitet')
    default:
      return t('Keine E-Rechnung im Anhang')
  }
}

/** Adresse des Rechnungspostfachs und offene Hinweise (#374). */
function MailboxCard({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const box = useLoad(() => einvoiceApi.mailbox(org.id), [org.id])
  const enabled = !!box.data?.enabled
  const hints = useLoad(
    () => (enabled ? einvoiceApi.mails(org.id) : Promise.resolve([])),
    [org.id, enabled],
  )
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (!enabled) return null
  const address = box.data?.address ?? ''
  async function copy() {
    try {
      await navigator.clipboard.writeText(address)
      setMessage({ kind: 'success', text: t('Adresse kopiert.') })
    } catch {
      setMessage({ kind: 'error', text: t('Kopieren ging nicht. Bitte die Adresse markieren.') })
    }
  }
  async function renew() {
    const yes = await confirmDialog({
      title: t('Neue Adresse vergeben?'),
      message: t(
        'Mails an die bisherige Adresse kommen dann nicht mehr im Rechnungseingang an. Teile die neue Adresse allen Lieferanten mit.',
      ),
      confirmLabel: t('Neue Adresse vergeben'),
    })
    if (!yes) return
    setBusy(true)
    setMessage(null)
    try {
      await einvoiceApi.renewMailbox(org.id)
      await box.reload()
      setMessage({ kind: 'success', text: t('Neue Adresse vergeben.') })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }
  async function dismiss(id: number) {
    setBusy(true)
    try {
      await einvoiceApi.dismissMail(org.id, id)
      await hints.reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card stack">
      <h2>{t('Rechnungspostfach')}</h2>
      <p>
        {t(
          'Lieferanten können E-Rechnungen an diese Adresse schicken. HUBIplan übernimmt XML-Anhänge und ZUGFeRD/Factur-X-PDFs jede Minute in den Rechnungseingang.',
        )}
      </p>
      <p>
        <strong>{address}</strong>
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="actions">
        <button className="button button-ghost" onClick={() => void copy()}>
          {t('Adresse kopieren')}
        </button>
        {canEdit && (
          <button className="button button-ghost" disabled={busy} onClick={() => void renew()}>
            {t('Neue Adresse vergeben')}
          </button>
        )}
      </div>
      {hints.error && <Alert kind="error">{hints.error}</Alert>}
      {!!hints.data?.length && (
        <>
          <h3>{t('Hinweise aus dem Postfach')}</h3>
          <ul className="stack">
            {hints.data.map((mail) => (
              <li key={mail.id}>
                <strong>{mailStatusText(mail)}</strong>
                <br />
                {formatDateTime(mail.received_at)} · {mail.sender || '—'}
                {mail.subject && <> · {mail.subject}</>}
                {mail.skipped.length > 0 && (
                  <>
                    <br />
                    <span className="muted small">
                      {mail.skipped
                        .map((part) =>
                          part.name
                            ? `${part.name} (${reasonText(part.reason)})`
                            : reasonText(part.reason),
                        )
                        .join(', ')}
                    </span>
                  </>
                )}
                {canEdit && (
                  <>
                    {' '}
                    <button
                      className="button button-ghost"
                      disabled={busy}
                      onClick={() => void dismiss(mail.id)}
                    >
                      {t('Erledigt')}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="muted small">
            {t(
              'Diese Mails liegen weiter im Postfach. Eine gewöhnliche PDF-Rechnung kannst du als Beleg in der Kasse ablegen.',
            )}
          </p>
        </>
      )}
    </div>
  )
}
