// Anschriftfelder einer E-Rechnung (Verkäufer und Käufer). Die Geschäftspartner selbst
// stehen unter pages/partners/.
import type { Party } from '../../api/einvoices.ts'
import { Field, SelectField } from '../../components/ui.tsx'
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
