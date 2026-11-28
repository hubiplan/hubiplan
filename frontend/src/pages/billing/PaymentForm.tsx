import { todayIso } from '../../api/members.ts'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { billingApi } from '../../api/billing.ts'
import { newRequestKey } from '../../api/client.ts'
import type { BillingSettings, Invoice } from '../../api/billing.ts'
import { financeApi, parseAmount } from '../../api/finance.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function PaymentForm({
  settings,
  invoice,
  onSaved,
}: {
  settings: BillingSettings
  invoice: Invoice
  onSaved: (inv: Invoice) => void
}) {
  const org = useActiveOrg()
  const bank = settings.accounts.find((a) => a.kind !== 'cash')
  const cash = settings.accounts.find((a) => a.kind === 'cash')
  const [method, setMethod] = useState<'transfer' | 'cash'>('transfer')
  const [account, setAccount] = useState(String(settings.account ?? bank?.id ?? ''))
  const [date, setDate] = useState(todayIso)
  const [amount, setAmount] = useState(invoice.outstanding.replace('.', ','))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Ein Schlüssel je Formular: erneutes Absenden bucht die Zahlung nicht doppelt
  const [requestKey] = useState(newRequestKey)
  const navigate = useNavigate()
  // Barzahlung mit unterschriebener Quittung (konzepte/digitale-quittung.md)
  const canSign = org.modules.includes('finance') && org.permissions.includes(PERM.financeEdit)

  async function sign() {
    setBusy(true)
    setError(null)
    try {
      const r = await financeApi.cashReceiptFromInvoice(org.id, invoice.id, {
        account: Number(account),
        amount: parseAmount(amount),
      })
      navigate(`/finanzen/quittungen/${r.id}`)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(
        await billingApi.addPayment(
          org.id,
          invoice.id,
          {
            date,
            amount: parseAmount(amount),
            method,
            account: Number(account),
          },
          requestKey,
        ),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="subcard" onSubmit={save}>
      <h3>{t('Zahlungseingang erfassen')}</h3>
      <div className="grid-3">
        <SelectField
          label={t('Zahlungsweg')}
          value={method}
          onChange={(e) => {
            const m = e.target.value as 'transfer' | 'cash'
            setMethod(m)
            const fit =
              m === 'cash'
                ? cash
                : (settings.accounts.find((a) => a.id === settings.account) ?? bank)
            if (fit) setAccount(String(fit.id))
          }}
        >
          <option value="transfer">{t('Überweisung')}</option>
          <option value="cash">{t('bar')}</option>
        </SelectField>
        <SelectField
          label={t('Konto')}
          value={account}
          onChange={(e) => setAccount(e.target.value)}
        >
          {settings.accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectField>
        <Field
          label={t('Datum')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Field
          label={t('Betrag (€)')}
          inputMode="decimal"
          required
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      <p className="muted small">
        {t('Die Zahlung wird automatisch als Einnahme in der Kasse gebucht.')}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy || !account}>
          {t('Zahlung buchen')}
        </button>
        {method === 'cash' && canSign && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy || !account}
            onClick={() => void sign()}
          >
            {t('Mit Unterschrift quittieren')}
          </button>
        )}
      </div>
      {method === 'cash' && canSign && (
        <p className="muted small">
          {t(
            '„Mit Unterschrift quittieren“ bucht die Zahlung erst, wenn beide auf dem Bildschirm unterschrieben haben. Das Datum ist dann der Tag der Unterschrift.',
          )}
        </p>
      )}
    </form>
  )
}
