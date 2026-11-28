import { sendingVersion } from '../../api/client.ts'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { billingApi } from '../../api/billing.ts'
import type { BillingSettings, Invoice } from '../../api/billing.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { alertDialog, choiceDialog, confirmDialog, promptDialog } from '../../components/dialog.ts'
import { Term } from '../../learning/Aids.tsx'
import { locale, t } from '../../i18n/index.ts'
import { StatusBadge } from './StatusBadge.tsx'
import { PaymentForm } from './PaymentForm.tsx'
import { InvoiceForm } from './InvoiceForm.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'

export function InvoiceDetail({
  id,
  settings,
  onClose,
  onChanged,
  onOpen,
  onDeleted,
}: {
  id: number
  settings: BillingSettings
  onClose: () => void
  onChanged: () => void
  /** eine andere Rechnung öffnen (z. B. den neuen Entwurf nach „Stornieren und neu anlegen“) */
  onOpen: (id: number) => void
  onDeleted: () => void
}) {
  const org = useActiveOrg()
  const { data: inv, error, setData } = useLoad(() => billingApi.invoice(org.id, id), [org.id, id])
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const canEdit = settings.can_edit

  // Sammelrechnungen haben eine Zeile je Mitglied: ab 20 Zeilen mit Suche, immer sortierbar
  const lineSearch = useRowSearch(inv?.lines ?? [], (l) => `${l.text} ${l.detail}`, t('Posten'))
  const lineSort = useRowSort(lineSearch.shown, {
    text: (l) => l.text,
    amount: (l) => Number(l.amount),
  })
  if (error) return <Alert kind="error">{error}</Alert>
  if (!inv) return <Loading />

  async function act(action: () => Promise<unknown>, text: string, deleted = false) {
    setBusy(true)
    setNotice(null)
    try {
      const result = await action()
      if (deleted) {
        onDeleted()
        return
      }
      if (result && typeof result === 'object' && 'id' in result) setData(result as Invoice)
      else setData(await billingApi.invoice(org.id, id))
      setNotice({ kind: 'success', text })
      onChanged()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function cancelInvoice(again: boolean) {
    if (!inv) return
    const paid = Number(inv.paid) > 0
    const reason = await promptDialog({
      title: t('Rechnung {number} stornieren?', { number: inv.number }),
      message: [
        t('Es entsteht eine Stornorechnung {number}-S, die die Rechnung vollständig aufhebt.', {
          number: inv.number,
        }),
        paid
          ? t('Bereits gezahlt: {x}. Das Guthaben erstattest oder verrechnest du danach.', {
              x: euro(inv.paid),
            })
          : '',
        again ? t('Danach öffnet sich eine Kopie der Rechnung als neuer Entwurf.') : '',
      ]
        .filter(Boolean)
        .join(' '),
      label: t('Grund (steht auf der Stornorechnung)'),
      confirmLabel: again ? t('Stornieren und neu anlegen') : t('Stornieren'),
      danger: true,
    })
    if (reason === null) return
    if (!again) {
      void act(() => billingApi.cancel(org.id, inv.id, reason), t('Storniert.'))
      return
    }
    setBusy(true)
    setNotice(null)
    try {
      await billingApi.cancel(org.id, inv.id, reason)
      const copy = await billingApi.copyInvoice(org.id, inv.id)
      onOpen(copy.id)
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
      setData(await billingApi.invoice(org.id, id))
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function copyAsDraft() {
    if (!inv) return
    setBusy(true)
    setNotice(null)
    try {
      const copy = await billingApi.copyInvoice(org.id, inv.id)
      onOpen(copy.id)
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function refund() {
    if (!inv) return
    if (
      await confirmDialog({
        title: t('Guthaben von {x} erstatten?', { x: euro(inv.credit) }),
        message: t(
          'Die Zahlungen werden in der Kasse storniert (Gegenbuchung mit heutigem Datum). Überweise den Betrag danach zurück.',
        ),
        confirmLabel: t('Erstatten'),
        danger: false,
      })
    )
      void act(() => billingApi.refundCredit(org.id, inv.id), t('Guthaben erstattet.'))
  }

  async function applyCredit() {
    if (!inv) return
    let targets
    try {
      targets = await billingApi.creditTargets(org.id, inv.id)
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
      return
    }
    if (targets.length === 0) {
      await alertDialog({
        title: t('Keine offene Rechnung'),
        message: t(
          'Für diesen Empfänger gibt es keine offene Rechnung. Lege zuerst die neue Rechnung an und schreibe sie fest, oder erstatte das Guthaben.',
        ),
      })
      return
    }
    const choice = await choiceDialog({
      title: t('Guthaben von {x} verrechnen mit …', { x: euro(inv.credit) }),
      choices: [
        ...targets.map((target) => ({
          value: String(target.id),
          label: `${target.number} · ${target.subject}`,
          hint: t('{date} · offen {x}', {
            date: formatDate(target.date),
            x: euro(target.outstanding),
          }),
        })),
        { value: '', label: t('Abbrechen') },
      ],
      cancelValue: '',
    })
    if (!choice) return
    void act(
      () => billingApi.applyCredit(org.id, inv.id, Number(choice)),
      t('Guthaben verrechnet.'),
    )
  }

  if (editing) {
    return (
      <InvoiceForm
        settings={settings}
        invoice={inv}
        onCancel={() => setEditing(false)}
        onSaved={(saved) => {
          setData(saved)
          setEditing(false)
          onChanged()
        }}
      />
    )
  }

  const collective = inv.recipient_kind === 'department'
  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>
          {inv.status === 'draft'
            ? t('Rechnungsentwurf')
            : t('Rechnung {number}', { number: inv.number })}{' '}
          <StatusBadge row={inv} />
        </h2>
        <button type="button" className="button button-ghost push-right" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      <div className="grid-2">
        <div>
          <p style={{ whiteSpace: 'pre-line' }}>
            <strong>{inv.recipient_name}</strong>
            {inv.recipient_address && `\n${inv.recipient_address}`}
          </p>
          <p className="muted small">{inv.recipient_email || t('keine E-Mail-Adresse bekannt')}</p>
        </div>
        <dl className="facts">
          <dt>{t('Betreff')}</dt>
          <dd>{inv.subject}</dd>
          <dt>{t('Rechnungsdatum')}</dt>
          <dd>{formatDate(inv.date)}</dd>
          <dt>{t('fällig')}</dt>
          <dd>{formatDate(inv.due_date)}</dd>
          {inv.run_label && (
            <>
              <dt>{t('Beitragslauf')}</dt>
              <dd>{inv.run_label}</dd>
            </>
          )}
          {inv.project_name && (
            <>
              <dt>{t('Veranstaltung')}</dt>
              <dd>{inv.project_name}</dd>
            </>
          )}
          {inv.sent_at && (
            <>
              <dt>{t('verschickt')}</dt>
              <dd>{formatDateTime(inv.sent_at)}</dd>
            </>
          )}
        </dl>
      </div>
      {lineSearch.field}
      <table className="table">
        <thead>
          <tr>
            {lineSort.head('text', collective ? t('Mitglied') : t('Posten'))}
            <th />
            {lineSort.head('amount', t('Betrag'), { className: 'num' })}
          </tr>
        </thead>
        <tbody>
          {lineSort.rows.map((l) => (
            <tr key={l.id}>
              <td>{l.text}</td>
              <td className="muted small">
                {l.detail}
                {l.vat_rate &&
                  t(' · {x} % USt', { x: Number(l.vat_rate).toLocaleString(locale()) })}
              </td>
              <td className="num">{euro(l.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th>{t('Gesamt')}</th>
            <th />
            <th className="num">{euro(inv.total)}</th>
          </tr>
          {Number(inv.prepaid ?? 0) > 0 && (
            <tr>
              <th>{t('Angerechnete Anzahlungen')}</th>
              <th />
              <th className="num">−{euro(inv.prepaid!)}</th>
            </tr>
          )}
          {inv.vat.map((v) => (
            <tr key={v.rate} className="muted small">
              <td>
                {t('darin')} {v.rate.replace('.', ',')} % <Term k="vat">{t('Umsatzsteuer')}</Term>
              </td>
              <td>
                {t('netto')} {euro(v.net)}
              </td>
              <td className="num">{euro(v.vat)}</td>
            </tr>
          ))}
          {(Number(inv.paid) > 0 || Number(inv.prepaid ?? 0) > 0) && (
            <tr>
              <th>{t('noch offen')}</th>
              <th />
              <th className="num">{euro(inv.outstanding)}</th>
            </tr>
          )}
        </tfoot>
      </table>
      {inv.note && <p style={{ whiteSpace: 'pre-line' }}>{inv.note}</p>}

      {inv.status === 'cancelled' && (
        <div className="card stack" data-testid="stornorechnung">
          <h3>
            {inv.cancellation_number
              ? t('Stornorechnung {number}', { number: inv.cancellation_number })
              : t('Storniert')}
          </h3>
          <p className="muted small">
            {inv.cancellation_date
              ? t('vom {date}', { date: formatDate(inv.cancellation_date) })
              : inv.cancelled_at && t('am {date}', { date: formatDateTime(inv.cancelled_at) })}
            {inv.cancellation_sent_at &&
              t(' · per E-Mail verschickt {date}', {
                date: formatDateTime(inv.cancellation_sent_at),
              })}
          </p>
          {inv.cancel_reason && <p>{t('Grund: {x}', { x: inv.cancel_reason })}</p>}
          {Number(inv.credit) > 0 && (
            <Alert kind="info">
              {t(
                'Guthaben {x}: Die Zahlungen hängen noch an der stornierten Rechnung. Erstatte den Betrag oder verrechne ihn mit einer offenen Rechnung.',
                { x: euro(inv.credit) },
              )}
            </Alert>
          )}
          <div className="button-row">
            {inv.has_cancellation_pdf && (
              <a
                className="button button-ghost"
                href={billingApi.cancellationPdfUrl(org.id, inv.id)}
                target="_blank"
                rel="noreferrer"
              >
                {t('Stornorechnung ansehen')}
              </a>
            )}
            {canEdit && inv.has_cancellation_pdf && inv.recipient_email && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  void act(
                    () => billingApi.sendCancellation(org.id, inv.id),
                    t('An {recipient_email} verschickt.', {
                      recipient_email: inv.recipient_email,
                    }),
                  )
                }
              >
                {inv.cancellation_sent_at
                  ? t('Stornorechnung erneut senden')
                  : t('Stornorechnung per E-Mail senden')}
              </button>
            )}
            {canEdit && Number(inv.credit) > 0 && (
              <>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void applyCredit()}
                >
                  {t('Verrechnen')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void refund()}
                >
                  {t('Erstatten')}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {inv.dunnings.length > 0 && (
        <>
          <h3>{t('Mahnungen')}</h3>
          <table className="table">
            <tbody>
              {inv.dunnings.map((d) => (
                <tr key={d.id}>
                  <td>{formatDate(d.date)}</td>
                  <td>
                    {d.name}
                    <div className="muted small">
                      {t('zahlbar bis')} {formatDate(d.due_date)}
                      {Number(d.fee) > 0 && t(' · Gebühr {x}', { x: euro(d.fee) })}
                      {d.sent_at
                        ? t(' · per E-Mail verschickt')
                        : t(' · nicht per E-Mail verschickt')}
                    </div>
                  </td>
                  <td className="actions">
                    <a
                      className="link-button"
                      href={billingApi.dunningPdfUrl(org.id, [d.id])}
                      target="_blank"
                      rel="noreferrer"
                    >
                      PDF
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {inv.payments.length > 0 && (
        <>
          <h3>{t('Zahlungen')}</h3>
          <table className="table">
            <tbody>
              {inv.payments.map((p) => (
                <tr key={p.id}>
                  <td>{formatDate(p.date)}</td>
                  <td>
                    {p.method_label} · {p.account_name}
                    <div className="muted small">
                      {t('Buchung')} {p.booking_number}
                    </div>
                  </td>
                  <td className="num">{euro(p.amount)}</td>
                  <td className="actions">
                    <a
                      className="link-button"
                      href={billingApi.receiptUrl(org.id, p.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t('Quittung')}
                    </a>
                    {canEdit && (
                      <button
                        type="button"
                        className="link-button"
                        disabled={busy}
                        onClick={async () => {
                          if (
                            await confirmDialog({
                              final: true,
                              title: t('Zahlung entfernen?'),
                              message: t(
                                'Die Zahlung und ihre Buchung in der Kasse werden entfernt.',
                              ),
                              confirmLabel: t('Entfernen'),
                            })
                          )
                            void act(
                              () => billingApi.deletePayment(org.id, p.id),
                              t('Zahlung entfernt.'),
                            )
                        }}
                      >
                        {t('Entfernen')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {canEdit && inv.status === 'open' && (
        <PaymentForm
          key={inv.outstanding}
          settings={settings}
          invoice={inv}
          onSaved={(saved) => {
            setData(saved)
            setNotice({
              kind: 'success',
              text: saved.status === 'paid' ? t('Bezahlt.') : t('Teilzahlung erfasst.'),
            })
            onChanged()
          }}
        />
      )}

      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      <div className="button-row">
        <a
          className="button button-ghost"
          href={billingApi.pdfUrl(org.id, inv.id)}
          target="_blank"
          rel="noreferrer"
        >
          {t('PDF ansehen')}
        </a>
        {canEdit && inv.status === 'draft' && (
          <>
            {inv.electronic_data && Object.keys(inv.electronic_data).length > 0 ? (
              <Link
                className="button button-ghost"
                to={`/finanzen/rechnungen/leistungen?rechnung=${inv.id}`}
              >
                {t('Leistungsrechnung bearbeiten')}
              </Link>
            ) : (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditing(true)}
              >
                {t('Bearbeiten')}
              </button>
            )}
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                void act(
                  () => sendingVersion(inv.version, () => billingApi.finalize(org.id, inv.id)),
                  t('Festgeschrieben.'),
                )
              }
            >
              {t('Festschreiben')}
            </button>
            <button
              type="button"
              className="button button-danger push-right"
              disabled={busy}
              onClick={async () => {
                if (
                  await confirmDialog({
                    final: false,
                    title: t('Entwurf löschen?'),
                    confirmLabel: t('Löschen'),
                  })
                )
                  void act(
                    () =>
                      sendingVersion(inv.version, () => billingApi.deleteInvoice(org.id, inv.id)),
                    '',
                    true,
                  )
              }}
            >
              {t('Löschen')}
            </button>
          </>
        )}
        {canEdit && inv.status === 'open' && inv.recipient_email && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              void act(
                () => billingApi.send(org.id, inv.id),
                t('An {recipient_email} verschickt.', { recipient_email: inv.recipient_email }),
              )
            }
          >
            {inv.sent_at ? t('Erneut per E-Mail senden') : t('Per E-Mail senden')}
          </button>
        )}
        {canEdit && inv.status === 'cancelled' && inv.copyable && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void copyAsDraft()}
          >
            {t('Als neuen Entwurf anlegen')}
          </button>
        )}
        {canEdit && (inv.status === 'open' || inv.status === 'paid') && (
          <>
            {inv.copyable && (
              <button
                type="button"
                className="button button-ghost push-right"
                disabled={busy}
                onClick={() => void cancelInvoice(true)}
              >
                {t('Stornieren und neu anlegen')}
              </button>
            )}
            <button
              type="button"
              className={inv.copyable ? 'button button-danger' : 'button button-danger push-right'}
              disabled={busy}
              onClick={() => void cancelInvoice(false)}
            >
              {t('Stornieren')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
