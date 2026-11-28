import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { billingApi } from '../../api/billing.ts'
import type { BillingSettings, FeeRateRow } from '../../api/billing.ts'
import { euro, parseAmount } from '../../api/finance.ts'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, SaveStatus, SelectField, Loading } from '../../components/ui.tsx'
import { useTerms } from '../../org/terms.ts'
import { HowTo, Term, Why } from '../../learning/Aids.tsx'
import { HouseholdFeeRulesCard } from './HouseholdFeeRules.tsx'
import { FeeProofDiscountsCard } from './FeeProofDiscounts.tsx'
import { WorkHoursCard } from './WorkHours.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useOrgBillingSettings } from './rulesHelpers.ts'

/** Beitragssätze: je Mitgliedsart (Verein) bzw. je gemeldetem Mitglied (Dachverband) und Altersstufen. */
export function FeeRulesPage() {
  const { org, settings } = useOrgBillingSettings()
  if (settings.error) return <Alert kind="error">{settings.error}</Alert>
  if (!settings.data) return <Loading />
  const s = settings.data
  const federation = s.org_type === 'federation'
  return (
    <div className="stack">
      {federation ? (
        <ClubRatesCard
          key={org.id}
          orgId={org.id}
          settings={s}
          onSaved={(d) => settings.setData(d)}
        />
      ) : (
        <FeesCard orgId={org.id} canEdit={s.can_edit} />
      )}
      <AgeRatesCard orgId={org.id} canEdit={s.can_edit} federation={federation} />
      {!federation && <SizeRatesCard orgId={org.id} canEdit={s.can_edit} />}
      {s.org_type === 'club' && <HouseholdFeeRulesCard orgId={org.id} canEdit={s.can_edit} />}
      {s.org_type === 'club' && <WorkHoursCard orgId={org.id} canEdit={s.can_edit} />}
      {/* bleibt leer, wenn die Einheit keine eigenen Mitglieder führt */}
      <FeeProofDiscountsCard orgId={org.id} canEdit={s.can_edit} />
    </div>
  )
}

function FeesCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const { data, error, setData } = useLoad(() => billingApi.fees(orgId), [orgId])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return <FeesForm orgId={orgId} rows={data} canEdit={canEdit} onSaved={setData} />
}

function FeesForm({
  orgId,
  rows,
  canEdit,
  onSaved,
}: {
  orgId: number
  rows: FeeRateRow[]
  canEdit: boolean
  onSaved: (rows: FeeRateRow[]) => void
}) {
  const form = useForm<Record<string, string>>(
    Object.fromEntries(
      rows.map((r) => [String(r.member_type), r.amount ? r.amount.replace('.', ',') : '']),
    ),
  )

  const auto = useAutoSave(
    form,
    (_changes, values) =>
      billingApi.saveFees(
        orgId,
        rows.map((r) => {
          const raw = values[String(r.member_type)]?.trim() ?? ''
          return { member_type: r.member_type, amount: raw ? parseAmount(raw) : null }
        }),
      ),
    { enabled: canEdit, onSaved: (result) => onSaved(result as FeeRateRow[]) },
  )

  return (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      <h2>{t('Jahresbeitrag je Mitgliedsart')}</h2>
      {canEdit && rows.length > 0 && <SaveStatus auto={auto} />}
      <HowTo k="calc_fee" />
      <p className="muted small">
        {t(
          'Der Betrag gilt für ein ganzes Geschäftsjahr. Bei halbjährlicher, vierteljährlicher oder monatlicher Abrechnung wird er aufgeteilt. Leer heißt beitragsfrei.',
        )}
      </p>
      {rows.length === 0 ? (
        <p className="muted">
          {t('Noch keine Mitgliedsarten. Lege sie zuerst hier an:')}{' '}
          <Link to="/mitglieder/einrichtung/mitgliedsarten">
            {t('Mitglieder → Einrichtung → Mitgliedsarten')}
          </Link>
          .
        </p>
      ) : (
        <div className="grid-3">
          {rows.map((r) => (
            <Field
              key={r.member_type}
              label={t('{name} (€ im Jahr)', { name: r.name })}
              inputMode="decimal"
              disabled={!canEdit}
              placeholder={t('beitragsfrei')}
              value={form.values[String(r.member_type)] ?? ''}
              error={form.errors[String(r.member_type)]}
              onChange={(e) => form.set(String(r.member_type), e.target.value)}
            />
          ))}
        </div>
      )}
    </form>
  )
}

function AgeRatesCard({
  orgId,
  canEdit,
  federation,
}: {
  orgId: number
  canEdit: boolean
  federation: boolean
}) {
  const tm = useTerms()
  const { data, error, reload } = useLoad(() => billingApi.ageRates(orgId), [orgId])
  const types = useLoad(
    () => (federation ? Promise.resolve([]) : billingApi.fees(orgId)),
    [orgId, federation],
  )
  const [message, setMessage] = useState<string | null>(null)
  const form = useForm({
    name: '',
    member_type: '',
    min_age: '',
    max_age: '',
    mode: 'discount',
    value: '',
  })
  const v = form.values

  async function add(e: FormEvent) {
    e.preventDefault()
    const value = parseAmount(v.value)
    const ok = await form.submit(
      () =>
        billingApi.createAgeRate(orgId, {
          name: v.name,
          member_type: v.member_type ? Number(v.member_type) : null,
          min_age: v.min_age ? Number(v.min_age) : null,
          max_age: v.max_age ? Number(v.max_age) : null,
          amount: v.mode === 'amount' ? value : null,
          discount_percent: v.mode === 'discount' ? value : null,
        }),
      t('Altersstufe angelegt.'),
    )
    if (ok) {
      form.setValues({ ...v, name: '', min_age: '', max_age: '', value: '' })
      await reload()
    }
  }

  async function remove(id: number) {
    setMessage(null)
    try {
      await billingApi.deleteAgeRate(orgId, id)
      await reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return null
  return (
    <div className="card card-wide">
      <h2>{t('Altersstufen')}</h2>
      <Why k="age_brackets" />
      <p className="muted small">
        {t('Zum Beispiel Jugend bis 17 Jahre mit halbem Beitrag. Maßgeblich ist das Alter am')}{' '}
        <Term k="cutoff_date">{t('Stichtag')}</Term>
        {t(', dem Beginn des Geschäftsjahres.')}
        {federation
          ? t(' Die Stufe gilt für die gemeldeten Mitglieder der {pl}.', { pl: tm.pl })
          : t(' Eine Stufe für eine bestimmte Mitgliedsart geht einer allgemeinen vor.')}
      </p>
      {data.length === 0 ? (
        <p className="muted">{t('Keine Altersstufen.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Stufe')}</th>
              <th>{t('Alter')}</th>
              <th>{t('gilt für')}</th>
              <th>{t('Beitrag')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.name}</strong>
                </td>
                <td>
                  {a.min_age !== null && a.max_age !== null
                    ? t('{min_age} bis {max_age} Jahre', { min_age: a.min_age, max_age: a.max_age })
                    : a.max_age !== null
                      ? t('bis {max_age} Jahre', { max_age: a.max_age })
                      : t('ab {min_age} Jahren', { min_age: a.min_age })}
                </td>
                <td>{a.member_type_name ?? t('alle Mitgliedsarten')}</td>
                <td>
                  {a.amount !== null
                    ? t('{x} im Jahr', { x: euro(a.amount) })
                    : t('{x} % Abschlag', {
                        x: Number(a.discount_percent).toLocaleString(locale()),
                      })}
                </td>
                <td className="actions">
                  {canEdit && (
                    <button type="button" className="link-button" onClick={() => void remove(a.id)}>
                      {t('Löschen')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      {canEdit && (
        <form className="subcard" onSubmit={add}>
          <h3>{t('Neue Altersstufe')}</h3>
          <div className="grid-3">
            <Field
              label={t('Bezeichnung')}
              required
              placeholder={t('z. B. Jugend')}
              value={v.name}
              error={form.errors.name}
              onChange={(e) => form.set('name', e.target.value)}
            />
            <Field
              label={t('ab Alter')}
              type="number"
              min={0}
              value={v.min_age}
              error={form.errors.min_age}
              onChange={(e) => form.set('min_age', e.target.value)}
            />
            <Field
              label={t('bis Alter (einschließlich)')}
              type="number"
              min={0}
              value={v.max_age}
              error={form.errors.max_age}
              onChange={(e) => form.set('max_age', e.target.value)}
            />
            {!federation && (
              <SelectField
                label={t('gilt für')}
                value={v.member_type}
                onChange={(e) => form.set('member_type', e.target.value)}
              >
                <option value="">{t('alle Mitgliedsarten')}</option>
                {(types.data ?? []).map((t) => (
                  <option key={t.member_type} value={t.member_type}>
                    {t.name}
                  </option>
                ))}
              </SelectField>
            )}
            <SelectField
              label={t('Beitrag')}
              value={v.mode}
              onChange={(e) => form.set('mode', e.target.value)}
            >
              <option value="discount">{t('Abschlag in Prozent')}</option>
              <option value="amount">
                {federation
                  ? t('eigener Betrag je Mitglied in €')
                  : t('eigener Jahresbeitrag in €')}
              </option>
            </SelectField>
            <Field
              label={v.mode === 'discount' ? t('Abschlag (%)') : t('Jahresbeitrag (€)')}
              inputMode="decimal"
              required
              value={v.value}
              error={form.errors.amount ?? form.errors.discount_percent}
              onChange={(e) => form.set('value', e.target.value)}
            />
          </div>
          {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </form>
      )}
    </div>
  )
}

/** Staffel nach Größe: Beitrag für Organisationsmitglieder nach Mitarbeitern, Einwohnern … */
function SizeRatesCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const { data, error, reload } = useLoad(() => billingApi.sizeRates(orgId), [orgId])
  const types = useLoad(() => billingApi.fees(orgId), [orgId])
  const [message, setMessage] = useState<string | null>(null)
  const form = useForm({ name: '', member_type: '', min_size: '', max_size: '', amount: '' })
  const v = form.values

  async function add(e: FormEvent) {
    e.preventDefault()
    const ok = await form.submit(
      () =>
        billingApi.createSizeRate(orgId, {
          name: v.name,
          member_type: v.member_type ? Number(v.member_type) : null,
          min_size: v.min_size ? Number(v.min_size) : null,
          max_size: v.max_size ? Number(v.max_size) : null,
          amount: parseAmount(v.amount),
        }),
      t('Größenstufe angelegt.'),
    )
    if (ok) {
      form.setValues({ ...v, name: '', min_size: '', max_size: '', amount: '' })
      await reload()
    }
  }

  async function remove(id: number) {
    setMessage(null)
    try {
      await billingApi.deleteSizeRate(orgId, id)
      await reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return null
  return (
    <div className="card card-wide size-rates">
      <h2>{t('Staffel nach Größe')}</h2>
      <HowTo k="calc_size_fee" />
      <p className="muted small">
        {t(
          'Für Organisationsmitglieder: Beitrag nach Größe, zum Beispiel Zahl der Mitarbeiter oder Einwohner. Die Größe steht in der Mitgliederakte. Organisationen ohne Größe zahlen den Beitrag ihrer Mitgliedsart.',
        )}
      </p>
      {data.length === 0 ? (
        <p className="muted">{t('Keine Größenstufen.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Stufe')}</th>
              <th>{t('Größe')}</th>
              <th>{t('gilt für')}</th>
              <th>{t('Beitrag')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.name}</strong>
                </td>
                <td>
                  {a.min_size !== null && a.max_size !== null
                    ? t('{min} bis {max}', { min: a.min_size, max: a.max_size })
                    : a.max_size !== null
                      ? t('bis {max}', { max: a.max_size })
                      : t('ab {min}', { min: a.min_size })}
                </td>
                <td>{a.member_type_name ?? t('alle Mitgliedsarten')}</td>
                <td>{t('{x} im Jahr', { x: euro(a.amount) })}</td>
                <td className="actions">
                  {canEdit && (
                    <button type="button" className="link-button" onClick={() => void remove(a.id)}>
                      {t('Löschen')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      {canEdit && (
        <form className="subcard" onSubmit={add}>
          <h3>{t('Neue Größenstufe')}</h3>
          <div className="grid-3">
            <Field
              label={t('Bezeichnung')}
              required
              placeholder={t('z. B. bis 50 Mitarbeiter')}
              value={v.name}
              error={form.errors.name}
              onChange={(e) => form.set('name', e.target.value)}
            />
            <Field
              label={t('ab Größe')}
              type="number"
              min={0}
              value={v.min_size}
              error={form.errors.min_size}
              onChange={(e) => form.set('min_size', e.target.value)}
            />
            <Field
              label={t('bis Größe (einschließlich)')}
              type="number"
              min={0}
              value={v.max_size}
              error={form.errors.max_size}
              onChange={(e) => form.set('max_size', e.target.value)}
            />
            <SelectField
              label={t('gilt für')}
              value={v.member_type}
              onChange={(e) => form.set('member_type', e.target.value)}
            >
              <option value="">{t('alle Mitgliedsarten')}</option>
              {(types.data ?? []).map((t) => (
                <option key={t.member_type} value={t.member_type}>
                  {t.name}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Jahresbeitrag (€)')}
              inputMode="decimal"
              required
              value={v.amount}
              error={form.errors.amount}
              onChange={(e) => form.set('amount', e.target.value)}
            />
          </div>
          {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </form>
      )}
    </div>
  )
}

function ClubRatesCard({
  orgId,
  settings,
  onSaved,
}: {
  orgId: number
  settings: BillingSettings
  onSaved: (s: BillingSettings) => void
}) {
  const tm = useTerms()
  const show = (x: string | null) => (x ? x.replace('.', ',') : '')
  const form = useForm({
    club_rate_active: show(settings.club_rate_active),
    club_rate_passive: show(settings.club_rate_passive),
    club_base_amount: show(settings.club_base_amount),
  })
  const v = form.values
  const canEdit = settings.can_edit

  const auto = useAutoSave(
    form,
    (changes) =>
      billingApi.updateSettings(
        orgId,
        Object.fromEntries(Object.entries(changes).map(([k, x]) => [k, x ? parseAmount(x) : null])),
      ),
    { enabled: canEdit, onSaved: (result) => onSaved(result as BillingSettings) },
  )

  return (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      <h2>
        {t('Verbandsbeitrag der')} {tm.pl}
      </h2>
      {canEdit && <SaveStatus auto={auto} />}
      <HowTo k="calc_federation_fee" />
      <p className="muted small">
        {t(
          'Jahresbetrag je gemeldetem Mitglied. Gezählt werden die Mitglieder, deren Mitgliedsart an {e_akk} gemeldet wird, am ersten Tag des Abrechnungszeitraums. Leer heißt kein Beitrag.',
          { e_akk: tm.e_akk },
        )}
      </p>
      <fieldset disabled={!canEdit}>
        <div className="grid-3">
          <Field
            label={t('je aktivem Mitglied (€ im Jahr)')}
            inputMode="decimal"
            value={v.club_rate_active}
            error={form.errors.club_rate_active}
            onChange={(e) => form.set('club_rate_active', e.target.value)}
          />
          <Field
            label={t('je passivem Mitglied (€ im Jahr)')}
            inputMode="decimal"
            value={v.club_rate_passive}
            error={form.errors.club_rate_passive}
            onChange={(e) => form.set('club_rate_passive', e.target.value)}
          />
          <Field
            label={t('Grundbetrag je {sg} (€ im Jahr)', { sg: tm.sg })}
            inputMode="decimal"
            value={v.club_base_amount}
            error={form.errors.club_base_amount}
            onChange={(e) => form.set('club_base_amount', e.target.value)}
          />
        </div>
      </fieldset>
    </form>
  )
}
