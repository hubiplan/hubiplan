// Arbeitsstunden mit Ersatzbeitrag (docs/arbeitsstunden.md): Pflichtstunden je Mitgliedsart,
// Altersgrenzen und der Stand je Mitglied. Geleistet zählt aus erledigten Helferschichten;
// fehlende Stunden kommen in den ersten Beitragslauf des folgenden Geschäftsjahres.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client.ts'
import { billingApi } from '../../api/billing.ts'
import type { WorkHours } from '../../api/billing.ts'
import { euro, parseAmount } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, Loading, SelectField } from '../../components/ui.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { locale, t } from '../../i18n/index.ts'

const comma = (v: string | null) => (v ? v.replace('.', ',').replace(/,00$/, '') : '')
const hours = (v: string) =>
  Number(v).toLocaleString(locale(), { minimumFractionDigits: 0, maximumFractionDigits: 2 })

export function WorkHoursCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const { data, error, setData } = useLoad(() => billingApi.workHours(orgId), [orgId])
  return (
    <section className="card card-wide stack" aria-label={t('Arbeitsstunden')}>
      <h2>{t('Arbeitsstunden')}</h2>
      <p className="muted small">
        {t(
          'Pflichtstunden je Mitgliedsart und Geschäftsjahr. Geleistet zählen erledigte Helferschichten. Wer weniger geleistet hat, bekommt im ersten Beitragslauf des folgenden Geschäftsjahres den Ersatzbeitrag als eigenen Posten. Wer nur einen Teil des Jahres Mitglied war, schuldet die Stunden anteilig je angefangenem Monat.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {!data && !error && <Loading />}
      {data && !data.helpers_on && (
        <Alert kind="info">
          {t(
            'Geleistete Stunden zählen aus Helferschichten. Schalte dafür das Modul Helferdienste ein; bis dahin berechnet der Beitragslauf keinen Ersatzbeitrag.',
          )}{' '}
          <Link to="/einstellungen/module">{t('Module einstellen')}</Link>
        </Alert>
      )}
      {data && (
        <WorkHoursForm
          key={JSON.stringify(data)}
          orgId={orgId}
          data={data}
          canEdit={canEdit}
          onSaved={setData}
        />
      )}
      {data?.helpers_on && data.rows.some((r) => r.hours) && (
        <BalanceTable orgId={orgId} years={data.years} />
      )}
    </section>
  )
}

function WorkHoursForm({
  orgId,
  data,
  canEdit,
  onSaved,
}: {
  orgId: number
  data: WorkHours
  canEdit: boolean
  onSaved: (d: WorkHours) => void
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      data.rows.flatMap((r) => [
        [`hours-${r.member_type}`, comma(r.hours)],
        [`rate-${r.member_type}`, comma(r.rate)],
      ]),
    ),
  )
  const [minAge, setMinAge] = useState(data.min_age === null ? '' : String(data.min_age))
  const [maxAge, setMaxAge] = useState(data.max_age === null ? '' : String(data.max_age))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (key: string, value: string) => setValues((v) => ({ ...v, [key]: value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    setErrors({})
    try {
      const saved = await billingApi.saveWorkHours(orgId, {
        min_age: minAge.trim() ? Number(minAge) : null,
        max_age: maxAge.trim() ? Number(maxAge) : null,
        rows: data.rows.map((r) => {
          const h = values[`hours-${r.member_type}`]?.trim() ?? ''
          const rate = values[`rate-${r.member_type}`]?.trim() ?? ''
          return {
            member_type: r.member_type,
            hours: h ? parseAmount(h) : null,
            rate: rate ? parseAmount(rate) : null,
          }
        }),
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

  if (data.rows.length === 0) return <p className="muted">{t('Noch keine Mitgliedsarten.')}</p>
  return (
    <form className="stack" onSubmit={submit}>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {data.rows.map((r) => (
        <div key={r.member_type} className="grid-2">
          <Field
            label={t('{name}: Pflichtstunden im Jahr', { name: r.name })}
            inputMode="decimal"
            placeholder={t('keine')}
            disabled={!canEdit}
            value={values[`hours-${r.member_type}`] ?? ''}
            error={errors[`hours-${r.member_type}`]}
            onChange={(e) => set(`hours-${r.member_type}`, e.target.value)}
          />
          <Field
            label={t('{name}: Ersatz je fehlender Stunde (€)', { name: r.name })}
            inputMode="decimal"
            placeholder="0"
            disabled={!canEdit || !values[`hours-${r.member_type}`]?.trim()}
            value={values[`rate-${r.member_type}`] ?? ''}
            error={errors[`rate-${r.member_type}`]}
            onChange={(e) => set(`rate-${r.member_type}`, e.target.value)}
          />
        </div>
      ))}
      <div className="grid-3">
        <Field
          label={t('Pflicht ab Alter')}
          type="number"
          min={0}
          max={120}
          placeholder={t('ohne Grenze')}
          disabled={!canEdit}
          value={minAge}
          error={errors.min_age}
          onChange={(e) => setMinAge(e.target.value)}
        />
        <Field
          label={t('Pflicht bis Alter')}
          type="number"
          min={0}
          max={120}
          placeholder={t('ohne Grenze')}
          hint={t('Alter zu Beginn des Geschäftsjahres')}
          disabled={!canEdit}
          value={maxAge}
          error={errors.max_age}
          onChange={(e) => setMaxAge(e.target.value)}
        />
      </div>
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

function BalanceTable({
  orgId,
  years,
}: {
  orgId: number
  years: { year: number; label: string }[]
}) {
  const [year, setYear] = useState(years[0]?.year ?? 0)
  const balance = useLoad(() => billingApi.workHourBalance(orgId, year), [orgId, year])
  const sort = useRowSort(balance.data?.people ?? [], {
    name: (p) => p.name,
    member_type: (p) => p.member_type,
    required: (p) => Number(p.required),
    done: (p) => Number(p.done),
    missing: (p) => Number(p.missing),
    amount: (p) => Number(p.amount),
  })
  return (
    <details className="stack">
      <summary>{t('Stand je Mitglied')}</summary>
      <SelectField
        label={t('Geschäftsjahr')}
        value={String(year)}
        onChange={(e) => setYear(Number(e.target.value))}
      >
        {years.map((y) => (
          <option key={y.year} value={y.year}>
            {y.label}
          </option>
        ))}
      </SelectField>
      {balance.error && <Alert kind="error">{balance.error}</Alert>}
      {!balance.data && !balance.error && <Loading />}
      {balance.data && balance.data.people.length === 0 && (
        <p className="muted">{t('In diesem Geschäftsjahr hat niemand Pflichtstunden.')}</p>
      )}
      {balance.data && balance.data.people.length > 0 && (
        <>
          <p className="muted small">
            {t(
              'Laufendes Jahr: Stand heute. Abgerechnet wird erst im ersten Beitragslauf des folgenden Geschäftsjahres.',
            )}
          </p>
          <table className="table">
            <thead>
              <tr>
                {sort.head('name', t('Name'))}
                {sort.head('member_type', t('Mitgliedsart'))}
                {sort.head('required', t('Soll'))}
                {sort.head('done', t('geleistet'))}
                {sort.head('missing', t('fehlen'))}
                {sort.head('amount', t('Ersatzbeitrag'))}
              </tr>
            </thead>
            <tbody>
              {sort.rows.map((p) => (
                <tr key={p.membership}>
                  <td>{p.name}</td>
                  <td>{p.member_type}</td>
                  <td>{hours(p.required)}</td>
                  <td>{hours(p.done)}</td>
                  <td>{hours(p.missing)}</td>
                  <td>{Number(p.amount) > 0 ? euro(p.amount) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>{t('Ersatzbeitrag zusammen: {total}', { total: euro(balance.data.total) })}</p>
        </>
      )}
    </details>
  )
}
