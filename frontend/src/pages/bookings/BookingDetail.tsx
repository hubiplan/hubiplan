import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { bookingApi } from '../../api/bookings.ts'
import type { BookableItem, Booking } from '../../api/bookings.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Term } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import './bookings.css'
import { span, statusLabel } from './format.ts'
import { BookingForm } from './BookingForm.tsx'
import { stamp } from './bookingsHelpers.ts'

export function BookingDetail({
  base,
  id,
  original,
  items,
  onClose,
  onChanged,
}: {
  base: string
  id: number
  original: string
  items: BookableItem[]
  onClose: () => void
  onChanged: () => Promise<void>
}) {
  const { data, error, reload } = useLoad(() => bookingApi.get(base, id), [base, id])
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await fn()
      await reload()
      await onChanged()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (error)
    return (
      <section className="card" aria-live="polite">
        <p>{t('Diese Buchung ist belegt; Einzelheiten sind nur für die Verwaltung sichtbar.')}</p>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </section>
    )
  if (!data) return <Loading />
  if (editing)
    return (
      <BookingForm
        base={base}
        items={items}
        booking={data}
        onDone={async (saved) => {
          setEditing(false)
          if (saved) {
            await reload()
            await onChanged()
          }
        }}
      />
    )
  const active = data.status === 'requested' || data.status === 'confirmed'
  return (
    <section className="card booking-detail" aria-live="polite">
      <div className="page-heading">
        <h2>{data.title}</h2>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      <p>
        {data.item_title} · {statusLabel(data.status)}
      </p>
      <p>{span(data)}</p>
      {data.repeat !== 'none' && (
        <p>
          {
            {
              weekly: t('wöchentlich'),
              monthly: t('monatlich'),
              yearly: t('jährlich'),
            }[data.repeat]
          }
          {data.repeat_until ? ` · ${t('bis {date}', { date: data.repeat_until })}` : ''}
        </p>
      )}
      {data.event_title && (
        <p>
          {t('Termin')}: <Link to={`/termine?termin=${data.event}`}>{data.event_title}</Link>
        </p>
      )}
      {data.competition_title && (
        <p>
          {t('Wettbewerb')}: {data.competition_title}
        </p>
      )}
      {data.note && <p>{data.note}</p>}
      {(data.contact.name || data.contact.email || data.contact.phone) && (
        <p>
          {t('Extern')}:{' '}
          {[data.contact.name, data.contact.email, data.contact.phone].filter(Boolean).join(' · ')}
        </p>
      )}
      {data.member_name && (
        <p>
          {t('Für Mitglied')}:{' '}
          {base.startsWith('/api/orgs/') ? (
            <Link to={`/mitglieder/${data.member}`}>{data.member_name}</Link>
          ) : (
            data.member_name
          )}
        </p>
      )}
      {data.booked_by && (
        <p className="muted">{t('Gebucht von {name}', { name: data.booked_by })}</p>
      )}
      {data.invoice && (
        <p>
          {t('Rechnung')}:{' '}
          <Link to={`/finanzen/rechnungen?rechnung=${data.invoice}`}>{data.invoice_number}</Link>
          {data.invoice_status === 'cancelled' ? ` · ${t('storniert')}` : ''}
        </p>
      )}
      {data.invoice &&
        data.invoice_status !== 'cancelled' &&
        (data.status === 'cancelled' || data.status === 'rejected') && (
          <Alert kind="info">
            {data.invoice_status === 'draft'
              ? t(
                  'Die Buchung gilt nicht mehr, der Rechnungsentwurf besteht noch. Lösche ihn unter Finanzen › Rechnungen, wenn die Miete entfällt.',
                )
              : t(
                  'Die Buchung gilt nicht mehr, die Rechnung besteht noch. Entfällt die Miete, storniere die Rechnung unter Finanzen › Rechnungen.',
                )}
          </Alert>
        )}
      {data.can_invoice && <InvoiceForm base={base} booking={data} disabled={busy} act={act} />}
      {data.needs_review && (
        <p role="status">
          {t(
            'Termin oder Rüstzeit haben sich geändert und die neue Zeit ist nicht frei. Bitte prüfen.',
          )}
        </p>
      )}
      {data.loan && data.status === 'confirmed' && (
        <Handover base={base} booking={data} busy={busy} act={act} />
      )}
      {failure && <p role="alert">{failure}</p>}
      {active && (
        <div className="button-row">
          {data.can_manage && data.status === 'requested' && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => act(() => bookingApi.decide(base, data, 'confirm'))}
            >
              {t('Bestätigen')}
            </button>
          )}
          {data.can_manage && data.status === 'requested' && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.decide(base, data, 'reject'))}
            >
              {t('Ablehnen')}
            </button>
          )}
          {data.can_cancel && !data.event && !data.competition && (
            <button className="button" disabled={busy} onClick={() => setEditing(true)}>
              {t('Bearbeiten')}
            </button>
          )}
          {data.can_cancel && data.repeat !== 'none' && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.skip(base, data, original))}
            >
              {t('Nur diesen Termin absagen')}
            </button>
          )}
          {data.can_cancel && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => {
                // Mit Rechnung: vorher sagen, dass sie bestehen bleibt (Gesamtaudit 19.11., F-01)
                const open = data.invoice && data.invoice_status !== 'cancelled'
                if (!open) return void act(() => bookingApi.decide(base, data, 'cancel'))
                void confirmDialog({
                  final: false,
                  title: t('Buchung mit Rechnung stornieren?'),
                  message: t(
                    'Zu dieser Buchung gibt es die Rechnung {number}. Sie bleibt bestehen: Einen Entwurf löschst du unter Finanzen › Rechnungen, eine gestellte Rechnung stornierst du dort.',
                    { number: data.invoice_number },
                  ),
                  confirmLabel: t('Buchung stornieren'),
                }).then((ok) => {
                  if (ok) void act(() => bookingApi.decide(base, data, 'cancel'))
                })
              }}
            >
              {data.repeat !== 'none' ? t('Ganze Serie stornieren') : t('Buchung stornieren')}
            </button>
          )}
        </div>
      )}
      {data.can_cancel && data.exceptions.length > 0 && (
        <details>
          <summary>{t('Abgesagte Termine')}</summary>
          <ul>
            {data.exceptions.map((e) => (
              <li key={e}>
                {span({ starts_at: e, ends_at: e, all_day: data.all_day })}{' '}
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => act(() => bookingApi.skip(base, data, e, true))}
                >
                  {t('Wieder aufnehmen')}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

/** „Rechnung anlegen“: Entwurf an das Mitglied, Betrag aus dem Mietpreis des Objekts. */
function InvoiceForm({
  base,
  booking,
  disabled,
  act,
}: {
  base: string
  booking: Booking
  disabled: boolean
  act: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState(booking.price_suggestion ?? '')
  const navigate = useNavigate()
  if (!open)
    return (
      <p>
        <button className="button button-ghost" disabled={disabled} onClick={() => setOpen(true)}>
          {t('Rechnung anlegen')}
        </button>
      </p>
    )
  return (
    <form
      className="booking-invoice"
      onSubmit={(e) => {
        e.preventDefault()
        void act(async () => {
          const saved = await bookingApi.invoice(base, booking, amount)
          if (saved.invoice) navigate(`/finanzen/rechnungen?rechnung=${saved.invoice}`)
        })
      }}
    >
      <p className="muted">
        {t(
          'Legt einen Rechnungsentwurf an {name} an, auch wenn der Beitrag sonst über eine Sammelrechnung läuft. Festschreiben und verschicken wie jede Rechnung.',
          { name: booking.member_name },
        )}
      </p>
      <label className="field">
        <span>{t('Betrag in Euro')}</span>
        <input
          required
          type="number"
          min="0.01"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <div className="button-row">
        <button className="button button-primary" disabled={disabled}>
          {t('Entwurf anlegen')}
        </button>
        <button
          className="button button-ghost"
          type="button"
          disabled={disabled}
          onClick={() => setOpen(false)}
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function Handover({
  base,
  booking,
  busy,
  act,
}: {
  base: string
  booking: Booking
  busy: boolean
  act: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const [update, setUpdate] = useState(false)
  const [condition, setCondition] = useState('ready')
  const [note, setNote] = useState('')
  const out = booking.handed_out_at
  const back = booking.returned_at
  return (
    <div className="booking-handover">
      <h3>
        <Term k="loan">{t('Ausleihe')}</Term>
      </h3>
      {out ? (
        <p>
          {t('Ausgegeben am {date}', { date: stamp(out) })}
          {booking.handed_out_by ? ` · ${booking.handed_out_by}` : ''}
        </p>
      ) : (
        <p>{t('Noch nicht ausgegeben.')}</p>
      )}
      {back && (
        <p>
          {t('Zurückgegeben am {date}', { date: stamp(back) })}
          {booking.returned_by ? ` · ${booking.returned_by}` : ''}
        </p>
      )}
      {booking.can_manage && out && !back && (
        <fieldset disabled={busy}>
          <label className="checkbox">
            <input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} />{' '}
            {t('Zustand des Materials bei der Rückgabe übernehmen')}
          </label>
          {update && (
            <>
              <label className="field">
                <span>{t('Zustand')}</span>
                <select value={condition} onChange={(e) => setCondition(e.target.value)}>
                  <option value="ready">{t('Einsatzbereit')}</option>
                  <option value="limited">{t('Eingeschränkt nutzbar')}</option>
                  <option value="defective">{t('Defekt')}</option>
                </select>
              </label>
              <label className="field">
                <span>{t('Hinweis zum Zustand')}</span>
                <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
              </label>
            </>
          )}
        </fieldset>
      )}
      {booking.can_manage && (
        <div className="button-row">
          {!out && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => act(() => bookingApi.handover(base, booking, 'out'))}
            >
              {t('Ausgabe bestätigen')}
            </button>
          )}
          {out && !back && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                act(() =>
                  bookingApi.handover(
                    base,
                    booking,
                    'return',
                    update ? { update_item: true, condition, condition_note: note } : {},
                  ),
                )
              }
            >
              {t('Rückgabe bestätigen')}
            </button>
          )}
          {out && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.handover(base, booking, 'undo'))}
            >
              {back ? t('Rückgabe zurücknehmen') : t('Ausgabe zurücknehmen')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
