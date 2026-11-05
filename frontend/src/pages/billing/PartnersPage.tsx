import { useState } from 'react'
import { einvoiceApi } from '../../api/einvoices.ts'
import type { Partner, Party } from '../../api/einvoices.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export const emptyParty = (): Party => ({
  name: '',
  street: '',
  postcode: '',
  city: '',
  country: 'DE',
  email: '',
  vat_id: '',
  tax_number: '',
  contact: '',
  phone: '',
  identifier: '',
})
export function PartyFields({
  value,
  onChange,
  title,
  disabled = false,
}: {
  value: Party
  onChange: (value: Party) => void
  title: string
  disabled?: boolean
}) {
  const fields: [keyof Party, string][] = [
    ['name', t('Name')],
    ['street', t('Straße und Hausnummer')],
    ['postcode', t('Postleitzahl')],
    ['city', t('Ort')],
    ['country', t('Ländercode')],
    ['email', t('E-Mail')],
    ['vat_id', t('USt-IdNr.')],
    ['tax_number', t('Steuernummer')],
    ['identifier', t('Eindeutige Geschäftspartnerkennung')],
    ['contact', t('Kontaktperson')],
    ['phone', t('Telefon')],
  ]
  return (
    <fieldset disabled={disabled} className="subcard">
      <legend>{title}</legend>
      <div className="form-grid">
        {fields.map(([key, label]) => (
          <Field
            key={key}
            label={label}
            value={value[key] ?? ''}
            type={key === 'email' ? 'email' : 'text'}
            required={['name', 'street', 'postcode', 'city', 'country', 'email'].includes(key)}
            onChange={(e) => onChange({ ...value, [key]: e.target.value })}
          />
        ))}
        <SelectField
          label={t('Schema der elektronischen Adresse')}
          value={value.endpoint_scheme === 'EM' || !value.endpoint_scheme ? 'EM' : 'EAS'}
          onChange={(e) =>
            onChange({
              ...value,
              endpoint_scheme: e.target.value === 'EM' ? 'EM' : '0204',
              endpoint_id: '',
            })
          }
        >
          <option value="EM">{t('E-Mail')}</option>
          <option value="EAS">{t('Registrierte Adresse (Peppol)')}</option>
        </SelectField>
        {value.endpoint_scheme && value.endpoint_scheme !== 'EM' && (
          <Field
            label={t('EAS-Schemacode')}
            required
            pattern="[0-9]{4}"
            value={value.endpoint_scheme}
            onChange={(e) => onChange({ ...value, endpoint_scheme: e.target.value })}
          />
        )}
        <Field
          label={t('Elektronische Adresse')}
          value={value.endpoint_id ?? ''}
          required={!!value.endpoint_scheme && value.endpoint_scheme !== 'EM'}
          onChange={(e) => onChange({ ...value, endpoint_id: e.target.value })}
        />
      </div>
      <p className="muted small">
        {t(
          'Ohne registrierte Adresse wird die E-Mail-Adresse verwendet. Peppol erfordert eine Registrierung beim Access Point.',
        )}
      </p>
    </fieldset>
  )
}

export function PartnersPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const load = useLoad(() => einvoiceApi.partners(org.id), [org.id])
  const [selected, setSelected] = useState<Partner | 'new' | null>(null)
  return (
    <div className="stack">
      <p>{t('Kunden und Lieferanten werden unabhängig von einer Mitgliedschaft verwaltet.')}</p>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {canEdit && (
        <button
          className="button button-primary"
          onClick={() =>
            void confirmLeave().then((ok) => {
              if (ok) setSelected('new')
            })
          }
        >
          {t('Geschäftspartner anlegen')}
        </button>
      )}
      {selected && (
        <PartnerForm
          key={selected === 'new' ? 'new' : selected.id}
          partner={selected === 'new' ? undefined : selected}
          canEdit={canEdit}
          onSaved={() => {
            setSelected(null)
            void load.reload()
          }}
          onClose={() => setSelected(null)}
        />
      )}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('Name')}</th>
              <th>{t('Kunde')}</th>
              <th>{t('Lieferant')}</th>
              <th>{t('Status')}</th>
            </tr>
          </thead>
          <tbody>
            {load.data?.map((partner) => (
              <tr key={partner.id}>
                <td>
                  <button
                    className="button button-ghost"
                    onClick={() =>
                      void confirmLeave().then((ok) => {
                        if (ok) setSelected(partner)
                      })
                    }
                  >
                    {partner.name}
                  </button>
                </td>
                <td>{partner.is_customer ? t('Ja') : '—'}</td>
                <td>{partner.is_supplier ? t('Ja') : '—'}</td>
                <td>{partner.is_active ? t('Aktiv') : t('Inaktiv')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {load.data?.length === 0 && <p>{t('Noch keine Geschäftspartner vorhanden.')}</p>}
      </div>
    </div>
  )
}

function PartnerForm({
  partner,
  canEdit,
  onSaved,
  onClose,
}: {
  partner?: Partner
  canEdit: boolean
  onSaved: () => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const [value, setValue] = useState(
    partner ?? {
      name: '',
      details: emptyParty(),
      is_customer: true,
      is_supplier: false,
      is_active: true,
    },
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [initial] = useState(() => JSON.stringify(value))
  useDraftGuard(canEdit && JSON.stringify(value) !== initial)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await einvoiceApi.savePartner(org.id, { ...value, name: value.details.name }, partner?.id)
          onSaved()
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <PartyFields
        title={t('Geschäftspartner')}
        value={value.details}
        onChange={(details) => setValue({ ...value, details })}
        disabled={!canEdit || busy}
      />
      <Checkbox
        label={t('Kunde')}
        checked={value.is_customer}
        disabled={!canEdit || busy}
        onChange={(is_customer) => setValue({ ...value, is_customer })}
      />
      <Checkbox
        label={t('Lieferant')}
        checked={value.is_supplier}
        disabled={!canEdit || busy}
        onChange={(is_supplier) => setValue({ ...value, is_supplier })}
      />
      <Checkbox
        label={t('Aktiv')}
        checked={value.is_active}
        disabled={!canEdit || busy}
        onChange={(is_active) => setValue({ ...value, is_active })}
      />
      <div className="actions">
        {canEdit && (
          <button className="button button-primary" disabled={busy}>
            {t('Speichern')}
          </button>
        )}
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          onClick={() =>
            void confirmLeave().then((ok) => {
              if (ok) onClose()
            })
          }
        >
          {t('Schließen')}
        </button>
      </div>
    </form>
  )
}
