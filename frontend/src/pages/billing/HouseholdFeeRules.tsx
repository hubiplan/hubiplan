// Familien- und Firmenbeitrag (Konzept Familien, Haushalte und Firmen, H3): wirkt auf die
// Summe der Einzelbeiträge einer Rechnung an einen Haushalt bzw. eine Firma.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client.ts'
import { parseAmount } from '../../api/finance.ts'
import { householdBillingApi } from '../../api/households.ts'
import type { FeeRuleMode, HouseholdFeeRule } from '../../api/households.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

const MODE_LABELS: Record<FeeRuleMode, string> = {
  none: t('keine Ermäßigung'),
  cap: t('Höchstbetrag je Rechnung'),
  flat: t('Pauschale'),
  stagger: t('Staffel (zweite Person, ab der dritten)'),
}

export function HouseholdFeeRulesCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const { data, error, setData } = useLoad(() => householdBillingApi.feeRules(orgId), [orgId])
  return (
    <section className="card card-wide" aria-label={t('Familien- und Firmenbeitrag')}>
      <h2>{t('Familien- und Firmenbeitrag')}</h2>
      <p className="muted small">
        {t(
          'Gilt für Rechnungen an einen Haushalt oder eine Firma (Mitglieder mit „Beitrag über den Haushalt“ und eingetragenem Zahler). Die Einzelbeiträge bleiben auf der Rechnung sichtbar, die Ermäßigung steht als eigener Posten darunter.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {!data && !error && <Loading />}
      {data?.map((rule) => (
        <RuleForm key={rule.kind} orgId={orgId} rule={rule} canEdit={canEdit} onSaved={setData} />
      ))}
    </section>
  )
}

function RuleForm({
  orgId,
  rule,
  canEdit,
  onSaved,
}: {
  orgId: number
  rule: HouseholdFeeRule
  canEdit: boolean
  onSaved: (rules: HouseholdFeeRule[]) => void
}) {
  const comma = (v: string | null) => (v ? v.replace('.', ',') : '')
  const [mode, setMode] = useState<FeeRuleMode>(rule.mode)
  const [amount, setAmount] = useState(comma(rule.amount))
  const [minPersons, setMinPersons] = useState(String(rule.min_persons))
  const [adult, setAdult] = useState(rule.adult_required)
  const [second, setSecond] = useState(comma(rule.second_percent))
  const [third, setThird] = useState(comma(rule.third_percent))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    setErrors({})
    try {
      const saved = await householdBillingApi.saveFeeRule(orgId, {
        kind: rule.kind,
        mode,
        amount: amount.trim() ? parseAmount(amount) : null,
        min_persons: Number(minPersons) || 1,
        adult_required: adult,
        second_percent: second.trim() ? parseAmount(second) : '0',
        third_percent: third.trim() ? parseAmount(third) : '0',
      })
      onSaved(saved)
      setMessage({ kind: 'success', text: t('Gespeichert.') })
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors)
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="subcard stack" onSubmit={submit}>
      <h3>{rule.kind === 'company' ? t('Firmenbeitrag') : t('Familienbeitrag')}</h3>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="grid-3">
        <SelectField
          label={t('Form')}
          value={mode}
          disabled={!canEdit}
          error={errors.mode}
          onChange={(e) => setMode(e.target.value as FeeRuleMode)}
        >
          {(Object.keys(MODE_LABELS) as FeeRuleMode[]).map((m) => (
            <option key={m} value={m}>
              {MODE_LABELS[m]}
            </option>
          ))}
        </SelectField>
        {(mode === 'cap' || mode === 'flat') && (
          <Field
            label={t('Betrag (€ im Jahr)')}
            inputMode="decimal"
            required
            disabled={!canEdit}
            value={amount}
            error={errors.amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        )}
        {mode === 'stagger' && (
          <>
            <Field
              label={t('zweite Person weniger (%)')}
              inputMode="decimal"
              disabled={!canEdit}
              value={second}
              error={errors.second_percent}
              onChange={(e) => setSecond(e.target.value)}
            />
            <Field
              label={t('ab der dritten Person weniger (%)')}
              inputMode="decimal"
              disabled={!canEdit}
              value={third}
              error={errors.third_percent}
              onChange={(e) => setThird(e.target.value)}
            />
          </>
        )}
        {mode !== 'none' && (
          <Field
            label={t('ab Personen')}
            type="number"
            min={1}
            disabled={!canEdit}
            value={minPersons}
            error={errors.min_persons}
            onChange={(e) => setMinPersons(e.target.value)}
          />
        )}
      </div>
      {mode !== 'none' && rule.kind === 'family' && (
        <Checkbox
          label={t('nur mit mindestens einem Erwachsenen')}
          checked={adult}
          disabled={!canEdit}
          onChange={setAdult}
        />
      )}
      {canEdit && (
        <div className="button-row">
          <button type="submit" className="button" disabled={busy}>
            {t('Speichern')}
          </button>
        </div>
      )}
    </form>
  )
}
