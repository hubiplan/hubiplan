import { euro } from '../../api/finance.ts'
import type { Booking, BookingKind } from '../../api/finance.ts'
import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

/** Wer das Geld bekommt (Ausgabe) bzw. zahlt (Einnahme). */
function partnerLabel(kind: BookingKind): string {
  return kind === 'expense' ? t('Empfänger') : t('Zahler')
}

function signedAmount(b: Booking, account: number | null): number {
  const amount = Number(b.amount)
  if (b.kind === 'income') return amount
  if (b.kind === 'expense') return -amount
  if (account !== null) return b.to_account === account ? amount : -amount
  return amount
}

export function BookingRow({
  booking: b,
  account,
  onOpen,
}: {
  booking: Booking
  account: number | null
  onOpen: () => void
}) {
  const value = signedAmount(b, account)
  const visible = b.receipts.filter((r) => !r.hidden_at).length
  return (
    <tr className={b.cancelled_by ? 'booking-cancelled' : undefined}>
      <td>
        <button type="button" className="link-button" onClick={onOpen}>
          {b.display_number}
        </button>
        {b.fixed && (
          <span className="muted" title={t('festgeschrieben')} aria-label={t('festgeschrieben')}>
            {' '}
            🔒
          </span>
        )}
      </td>
      <td>{formatDate(b.date)}</td>
      <td>
        {b.text}
        {b.cancelled_by && (
          <div className="small">
            {t('storniert durch')} {b.cancelled_by.number}
          </div>
        )}
        {b.split && (
          <div className="small">
            {b.split.is_lead
              ? t('aufgeteilt, weitere Teile: {numbers}', {
                  numbers: b.split.parts.map((p) => p.number).join(', '),
                })
              : t('Teil von {number}', { number: b.split.lead.number })}
          </div>
        )}
        <div className="muted small">
          {[
            b.counterparty
              ? t('{x}: {counterparty}', { x: partnerLabel(b.kind), counterparty: b.counterparty })
              : null,
            b.reference,
            b.member_name,
            b.department_name,
            b.project_name,
          ]
            .filter(Boolean)
            .join(' · ')}
        </div>
      </td>
      <td>
        {b.kind === 'transfer'
          ? t('{account_name} → {to_account_name}', {
              account_name: b.account_name,
              to_account_name: b.to_account_name,
            })
          : b.account_name}
      </td>
      <td>
        {b.kind === 'transfer' ? <span className="muted">{t('Umbuchung')}</span> : b.category_name}
      </td>
      <td
        className={`num ${
          b.kind === 'transfer' && account === null ? '' : value < 0 ? 'amount-out' : 'amount-in'
        }`}
      >
        {euro(b.kind === 'transfer' && account === null ? Number(b.amount) : value)}
      </td>
      <td>{visible > 0 ? t('📎 {visible}', { visible }) : <span className="muted">–</span>}</td>
    </tr>
  )
}
