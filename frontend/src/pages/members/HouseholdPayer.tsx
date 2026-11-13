// Zahler eines Haushalts bzw. einer Firma (Konzept Familien, Haushalte und Firmen, H2):
// Wer die gemeinsame Beitragsrechnung bekommt, und das Lastschriftmandat dafür.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { sepaApi } from '../../api/billing.ts'
import { ApiError } from '../../api/client.ts'
import { einvoiceApi } from '../../api/einvoices.ts'
import { householdBillingApi } from '../../api/households.ts'
import type {
  Household,
  HouseholdPayer,
  HouseholdPayerData,
  PayerKind,
} from '../../api/households.ts'
import { todayIso } from '../../api/members.ts'
import type { MemberRow } from '../../api/members.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { Alert, Field, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

const KIND_LABELS: Record<PayerKind, string> = {
  member: t('Mitglied'),
  external: t('Person ohne Mitgliedschaft'),
  organization: t('Organisationsmitglied'),
  partner: t('Geschäftspartner'),
}

/** Zahler und Mandat, aufklappbar unter der Karte des Haushalts. */
export function HouseholdPayerPanel({
  orgId,
  household,
  canEdit,
}: {
  orgId: number
  household: Household
  canEdit: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="stack">
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? t('Zahler ausblenden') : t('Zahler und Mandat')}
        </button>
      </div>
      {open && <PayerDetails orgId={orgId} household={household} canEdit={canEdit} />}
    </div>
  )
}

function PayerDetails({
  orgId,
  household,
  canEdit,
}: {
  orgId: number
  household: Household
  canEdit: boolean
}) {
  const { data, error, setData, reload } = useLoad(
    () => householdBillingApi.payer(orgId, household.id),
    [orgId, household.id],
  )
  const [editing, setEditing] = useState(false)
  const [addingMandate, setAddingMandate] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  const payer = data.payer
  const ownMandate = payer !== null && (payer.kind === 'external' || payer.kind === 'partner')

  async function remove() {
    const ok = await confirmDialog({
      title: t('Zahler entfernen?'),
      message: t(
        'Die Beiträge gehen dann wieder einzeln an die Mitglieder. Schon erstellte Rechnungen bleiben.',
      ),
      confirmLabel: t('Entfernen'),
    })
    if (!ok) return
    try {
      await householdBillingApi.removePayer(orgId, household.id)
      setMessage(t('Zahler entfernt.'))
      void reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <div className="subcard stack">
      <h3>{t('Zahler')}</h3>
      {message && <Alert kind="success">{message}</Alert>}
      {editing ? (
        <PayerForm
          orgId={orgId}
          household={household}
          payer={payer}
          onDone={(saved) => {
            setEditing(false)
            if (saved) {
              setData(saved)
              setMessage(t('Zahler gespeichert.'))
            }
          }}
        />
      ) : (
        <>
          {payer ? (
            <p>
              <strong>{payerName(payer)}</strong>{' '}
              <span className="muted small">{KIND_LABELS[payer.kind]}</span>
            </p>
          ) : (
            <p className="muted">
              {t(
                'Noch kein Zahler. Beiträge von Mitgliedern mit „Beitrag über den Haushalt“ gehen bis dahin einzeln.',
              )}
            </p>
          )}
          {canEdit && (
            <div className="button-row">
              <button type="button" className="button" onClick={() => setEditing(true)}>
                {payer ? t('Zahler ändern') : t('Zahler eintragen')}
              </button>
              {payer && (
                <button type="button" className="button button-ghost" onClick={() => void remove()}>
                  {t('Zahler entfernen')}
                </button>
              )}
            </div>
          )}
        </>
      )}
      {payer && (
        <>
          <h4>{t('Lastschriftmandat')}</h4>
          {!ownMandate && (
            <p className="muted small">{t('Es gilt das Mandat des zahlenden Mitglieds.')}</p>
          )}
          {data.mandates.length === 0 ? (
            <p className="muted small">{t('Kein Mandat hinterlegt.')}</p>
          ) : (
            <ul className="item-list">
              {data.mandates.map((m) => (
                <li key={m.id} className="item-row">
                  <div className="item-row-info">
                    {m.reference} · {m.iban_masked}{' '}
                    <span className="muted small">
                      {m.status_label}, {t('seit {date}', { date: formatDate(m.signed_on) })}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {canEdit &&
            ownMandate &&
            (addingMandate ? (
              <MandateForm
                orgId={orgId}
                household={household}
                payer={payer}
                onDone={(changed) => {
                  setAddingMandate(false)
                  if (changed) void reload()
                }}
              />
            ) : (
              <div className="button-row">
                <button type="button" className="button" onClick={() => setAddingMandate(true)}>
                  {t('Mandat erfassen')}
                </button>
              </div>
            ))}
        </>
      )}
    </div>
  )
}

function payerName(p: HouseholdPayer): string {
  if (p.kind === 'member' || p.kind === 'organization') return p.membership_name
  if (p.kind === 'partner') return p.partner_name
  return p.name
}

const EMPTY: HouseholdPayer = {
  kind: 'member',
  membership: null,
  membership_name: '',
  partner: null,
  partner_name: '',
  name: '',
  attention: '',
  street: '',
  postal_code: '',
  city: '',
  country: '',
  email: '',
  order_reference: '',
  leitweg_id: '',
}

function PayerForm({
  orgId,
  household,
  payer,
  onDone,
}: {
  orgId: number
  household: Household
  payer: HouseholdPayer | null
  onDone: (saved: HouseholdPayerData | null) => void
}) {
  const company = household.kind === 'company'
  const [values, setValues] = useState<HouseholdPayer>(
    payer ?? { ...EMPTY, kind: company ? 'organization' : 'member' },
  )
  const [member, setMember] = useState<MemberRow | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const partners = useLoad(
    () => (values.kind === 'partner' ? einvoiceApi.partners(orgId) : Promise.resolve([])),
    [orgId, values.kind],
  )
  const set = (key: keyof HouseholdPayer, value: string | number | null) =>
    setValues((v) => ({ ...v, [key]: value }))
  const byMember = values.kind === 'member' || values.kind === 'organization'

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setErrors({})
    try {
      onDone(
        await householdBillingApi.savePayer(orgId, household.id, {
          ...values,
          membership: byMember ? (member?.id ?? values.membership) : null,
          partner: values.kind === 'partner' ? values.partner : null,
        }),
      )
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      {error && <Alert kind="error">{error}</Alert>}
      <SelectField
        label={t('Wer zahlt?')}
        value={values.kind}
        error={errors.kind}
        onChange={(e) => set('kind', e.target.value)}
      >
        {(Object.keys(KIND_LABELS) as PayerKind[]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABELS[k]}
          </option>
        ))}
      </SelectField>
      {byMember && (
        <>
          <MemberPicker
            orgId={orgId}
            value={member}
            onChange={setMember}
            label={
              values.kind === 'organization' ? t('Organisationsmitglied') : t('zahlendes Mitglied')
            }
          />
          {!member && values.membership_name && (
            <p className="muted small">{t('bisher: {name}', { name: values.membership_name })}</p>
          )}
          {errors.membership && <Alert kind="error">{errors.membership}</Alert>}
        </>
      )}
      {values.kind === 'partner' && (
        <SelectField
          label={t('Geschäftspartner')}
          value={values.partner ?? ''}
          error={errors.partner}
          onChange={(e) => set('partner', e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t('bitte wählen')}</option>
          {(partners.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
      )}
      {values.kind === 'external' && (
        <div className="grid-3">
          <Field
            label={t('Name')}
            required
            value={values.name}
            error={errors.name}
            onChange={(e) => set('name', e.target.value)}
          />
          <Field
            label={t('Straße oder Postfach')}
            value={values.street}
            error={errors.street}
            onChange={(e) => set('street', e.target.value)}
          />
          <Field
            label={t('PLZ')}
            value={values.postal_code}
            error={errors.postal_code}
            onChange={(e) => set('postal_code', e.target.value)}
          />
          <Field
            label={t('Ort')}
            value={values.city}
            error={errors.city}
            onChange={(e) => set('city', e.target.value)}
          />
          <Field
            label={t('E-Mail-Adresse')}
            type="email"
            value={values.email}
            error={errors.email}
            onChange={(e) => set('email', e.target.value)}
          />
        </div>
      )}
      <div className="grid-3">
        <Field
          label={t('z. Hd. (optional)')}
          value={values.attention}
          error={errors.attention}
          onChange={(e) => set('attention', e.target.value)}
        />
        {values.kind !== 'external' && (
          <Field
            label={t('Rechnungs-E-Mail (optional)')}
            type="email"
            value={values.email}
            error={errors.email}
            onChange={(e) => set('email', e.target.value)}
          />
        )}
        {company && (
          <>
            <Field
              label={t('Bestellnummer (optional)')}
              value={values.order_reference}
              error={errors.order_reference}
              onChange={(e) => set('order_reference', e.target.value)}
            />
            <Field
              label={t('Leitweg-ID (optional)')}
              value={values.leitweg_id}
              error={errors.leitweg_id}
              onChange={(e) => set('leitweg_id', e.target.value)}
            />
          </>
        )}
      </div>
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function MandateForm({
  orgId,
  household,
  payer,
  onDone,
}: {
  orgId: number
  household: Household
  payer: HouseholdPayer
  onDone: (changed: boolean) => void
}) {
  const [holder, setHolder] = useState(payerName(payer))
  const [iban, setIban] = useState('')
  const [bic, setBic] = useState('')
  const [signedOn, setSignedOn] = useState(todayIso)
  const [scheme, setScheme] = useState<'CORE' | 'B2B'>('CORE')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setErrors({})
    try {
      await sepaApi.createMandate(orgId, {
        household: household.id,
        holder,
        iban,
        bic,
        signed_on: signedOn,
        scheme: payer.kind === 'partner' ? scheme : 'CORE',
      })
      onDone(true)
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors)
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="grid-3">
        <Field
          label={t('Kontoinhaber')}
          required
          value={holder}
          error={errors.holder}
          onChange={(e) => setHolder(e.target.value)}
        />
        <Field
          label="IBAN"
          required
          value={iban}
          error={errors.iban}
          onChange={(e) => setIban(e.target.value)}
        />
        <Field
          label={t('BIC (optional)')}
          value={bic}
          error={errors.bic}
          onChange={(e) => setBic(e.target.value)}
        />
        <Field
          label={t('unterschrieben am')}
          type="date"
          required
          value={signedOn}
          error={errors.signed_on}
          onChange={(e) => setSignedOn(e.target.value)}
        />
        {payer.kind === 'partner' && (
          <SelectField
            label={t('Verfahren')}
            value={scheme}
            error={errors.scheme}
            onChange={(e) => setScheme(e.target.value as 'CORE' | 'B2B')}
          >
            <option value="CORE">{t('Basislastschrift')}</option>
            <option value="B2B">{t('Firmenlastschrift (B2B)')}</option>
          </SelectField>
        )}
      </div>
      <p className="muted small">
        {t(
          'Das unterschriebene Formular bitte aufbewahren. Ein neues Mandat ersetzt ein älteres des gleichen Zahlers.',
        )}
      </p>
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
