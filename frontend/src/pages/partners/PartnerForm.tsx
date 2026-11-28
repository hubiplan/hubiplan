import { useState } from 'react'
import { Link } from 'react-router-dom'
import { financeApi } from '../../api/finance.ts'
import { PARTNER_KINDS, PARTNER_ROLES, partnerApi, partnerFieldApi } from '../../api/partners.ts'
import type { BusinessPartner, PartnerInput, PartnerKind, PartnerRole } from '../../api/partners.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { FieldsTab } from '../members/FieldsTab.tsx'
import { TextArea } from '../settings/TextArea.tsx'
import { Agreements } from './Agreements.tsx'
import { PartnerDocuments } from './PartnerDocuments.tsx'
import { kindLabel, partnerAccess, roleLabel } from './access.ts'
import { useRevealFocus } from '../../components/revealFocus.ts'
import { Contacts } from './Contacts.tsx'

const emptyPartner = (): PartnerInput => ({
  kind: 'company',
  roles: [],
  details: {
    name: '',
    street: '',
    postcode: '',
    city: '',
    country: 'DE',
    email: '',
    phone: '',
    website: '',
    vat_id: '',
    tax_number: '',
    contact: '',
    identifier: '',
  },
  our_customer_number: '',
  first_contact_on: null,
  first_contact_note: '',
  liaison: null,
  notes: '',
  website_consent: false,
  website_url: '',
  is_active: true,
})

export function PartnerForm({
  partner,
  others,
  onSaved,
  onChanged,
  onClose,
}: {
  partner?: BusinessPartner
  others: BusinessPartner[]
  onSaved: (saved?: BusinessPartner) => void
  /** Nach jedem automatischen Speichern (Liste auffrischen) */
  onChanged?: () => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const access = partnerAccess(org.permissions)
  const canEdit = access.edit
  const financeOn = org.modules.includes('finance') && org.permissions.includes('finance.view')
  const hasWebsite = org.modules.includes('website')
  const [value, setValue] = useState<PartnerInput>(() =>
    partner
      ? {
          kind: partner.kind,
          roles: partner.roles,
          details: { ...emptyPartner().details!, ...partner.details },
          our_customer_number: partner.our_customer_number,
          first_contact_on: partner.first_contact_on,
          first_contact_note: partner.first_contact_note,
          liaison: partner.liaison,
          notes: partner.notes,
          website_consent: partner.website_consent,
          website_url: partner.website_url,
          is_active: partner.is_active,
          ...(partner.bank !== undefined
            ? {
                bank: partner.bank,
                default_category: partner.default_category ?? null,
                payment_terms_days: partner.payment_terms_days ?? null,
                artist: partner.artist ?? false,
              }
            : {}),
        }
      : emptyPartner(),
  )
  const categories = useLoad(
    () => (access.money ? financeApi.categories(org.id) : Promise.resolve([])),
    [org.id, access.money],
  )
  const [liaison, setLiaison] = useState<PickedMember | null>(() =>
    partner?.liaison
      ? { id: partner.liaison, first_name: '', last_name: partner.liaison_name }
      : null,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [mergeWith, setMergeWith] = useState('')
  const [initial] = useState(() => JSON.stringify(value))
  const [, setErrors] = useState<Record<string, string>>({})
  // Bestehende Geschäftspartner speichern automatisch (nur geänderte Teile),
  // neue erst mit „Anlegen“
  const auto = useAutoSave(
    { values: value, setErrors, setValues: setValue },
    (changes) => partnerApi.save(org.id, changes, partner!.id),
    {
      enabled: !!partner && canEdit,
      onSaved: () => onChanged?.(),
    },
  )
  useDraftGuard(!partner && canEdit && JSON.stringify(value) !== initial)
  const details = value.details!
  const setDetail = (key: keyof typeof details, v: string) =>
    setValue((cur) => ({ ...cur, details: { ...cur.details!, [key]: v } }))
  const setBank = (key: 'iban' | 'bic' | 'holder', v: string) =>
    setValue((cur) => ({
      ...cur,
      bank: { ...(cur.bank ?? { iban: '', bic: '', holder: '' }), [key]: v },
    }))
  const toggleRole = (r: PartnerRole, on: boolean) =>
    setValue((cur) => {
      const roles = new Set(cur.roles ?? [])
      if (on) roles.add(r)
      else roles.delete(r)
      return { ...cur, roles: PARTNER_ROLES.filter((x) => roles.has(x)) }
    })
  const disabled = !canEdit || busy
  const moneyDisabled = disabled || !access.moneyEdit
  const detailFields: [keyof typeof details, string, string?][] = [
    ['name', t('Name')],
    ['street', t('Straße und Hausnummer')],
    ['postcode', t('Postleitzahl')],
    ['city', t('Ort')],
    ['country', t('Ländercode')],
    ['email', t('E-Mail'), 'email'],
    ['phone', t('Telefon'), 'tel'],
    ['website', t('Webseite'), 'url'],
    ['vat_id', t('USt-IdNr.')],
    ['tax_number', t('Steuernummer')],
    ['leitweg_id', t('Leitweg-ID')],
  ]
  // VW-43: neu eingeblendetes Formular bekommt den Fokus und rückt ins Bild
  const formRef = useRevealFocus<HTMLFormElement>(!partner, () => {
    void confirmLeave().then((ok) => {
      if (ok) onClose()
    })
  })
  return (
    <form
      className="card stack"
      ref={formRef}
      onSubmit={async (e) => {
        e.preventDefault()
        if (partner) return
        setBusy(true)
        setError('')
        try {
          const saved = await partnerApi.save(org.id, value)
          onSaved(saved)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h3>
        {partner
          ? `${partner.number ? `${partner.number} · ` : ''}${partner.name}`
          : t('Neuer Geschäftspartner')}
      </h3>
      {partner && canEdit && <SaveStatus auto={auto} />}
      {error && <Alert kind="error">{error}</Alert>}
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Übersicht')}</legend>
        <div className="form-grid">
          <SelectField
            label={t('Art')}
            value={value.kind}
            onChange={(e) => setValue((cur) => ({ ...cur, kind: e.target.value as PartnerKind }))}
          >
            {PARTNER_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </SelectField>
          {detailFields.map(([key, label, type]) => (
            <Field
              key={key}
              label={label}
              type={type ?? 'text'}
              required={key === 'name'}
              value={details[key] ?? ''}
              onChange={(e) => setDetail(key, e.target.value)}
            />
          ))}
          <Field
            label={t('Unsere Kundennummer dort')}
            value={value.our_customer_number ?? ''}
            onChange={(e) => setValue((cur) => ({ ...cur, our_customer_number: e.target.value }))}
          />
        </div>
        {value.kind === 'person' && (
          <p className="muted small">
            {t(
              'Privatpersonen nur für die Abwicklung von Verträgen speichern. Ist die Person Mitglied, bitte nicht doppelt anlegen.',
            )}
          </p>
        )}
        {value.kind === 'person' && <Why k="partner_person" />}
        {partner?.membership_name && (
          <p className="small">{t('Auch Mitglied: {name}', { name: partner.membership_name })}</p>
        )}
      </fieldset>
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Rollen')}</legend>
        <div className="grid-3">
          {PARTNER_ROLES.map((r) => (
            <Checkbox
              key={r}
              label={roleLabel(r)}
              checked={(value.roles ?? []).includes(r)}
              disabled={disabled}
              onChange={(on) => toggleRole(r, on)}
            />
          ))}
        </div>
      </fieldset>
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Kontakt zum Verein')}</legend>
        <div className="form-grid">
          <Field
            label={t('Erstkontakt am')}
            type="date"
            value={value.first_contact_on ?? ''}
            onChange={(e) =>
              setValue((cur) => ({ ...cur, first_contact_on: e.target.value || null }))
            }
          />
          <Field
            label={t('Erstkontakt')}
            hint={t('Wie und wo, z. B. Sommerfest 2026')}
            maxLength={300}
            value={value.first_contact_note ?? ''}
            onChange={(e) => setValue((cur) => ({ ...cur, first_contact_note: e.target.value }))}
          />
          {canEdit ? (
            <MemberPicker
              orgId={org.id}
              label={t('Betreut von')}
              value={liaison}
              onChange={(m) => {
                setLiaison(m)
                setValue((cur) => ({ ...cur, liaison: m?.id ?? null }))
              }}
            />
          ) : (
            <div className="field">
              <span>{t('Betreut von')}</span>
              <p>{partner?.liaison_name || t('niemand')}</p>
            </div>
          )}
        </div>
      </fieldset>
      {value.bank !== undefined || (!partner && access.money) ? (
        <fieldset disabled={moneyDisabled} className="subcard">
          <legend>{t('Kasse')}</legend>
          <div className="form-grid">
            <Field
              label={t('IBAN')}
              value={value.bank?.iban ?? ''}
              onChange={(e) => setBank('iban', e.target.value)}
            />
            <Field
              label={t('BIC')}
              value={value.bank?.bic ?? ''}
              onChange={(e) => setBank('bic', e.target.value)}
            />
            <Field
              label={t('Kontoinhaber')}
              value={value.bank?.holder ?? ''}
              onChange={(e) => setBank('holder', e.target.value)}
            />
            <SelectField
              label={t('Standardkategorie')}
              hint={t('Wird beim Buchen vorgeschlagen')}
              value={value.default_category ?? ''}
              onChange={(e) =>
                setValue((cur) => ({
                  ...cur,
                  default_category: e.target.value ? Number(e.target.value) : null,
                }))
              }
            >
              <option value="">{t('keine')}</option>
              {(categories.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Zahlungsziel in Tagen')}
              type="number"
              min={0}
              max={365}
              value={value.payment_terms_days ?? ''}
              onChange={(e) =>
                setValue((cur) => ({
                  ...cur,
                  payment_terms_days: e.target.value ? Number(e.target.value) : null,
                }))
              }
            />
          </div>
          {partner?.bank?.changed_at && (
            <p className="muted small">
              {t('Bankverbindung zuletzt geändert am {date} von {name}.', {
                date: formatDay(partner.bank.changed_at),
                name: partner.bank.changed_by ?? '',
              })}
            </p>
          )}
          {/* Künstlersozialabgabe gehört zum Modul Steuern; ein gesetztes Kennzeichen bleibt sichtbar */}
          {(org.modules.includes('tax') || !!value.artist) && (
            <Checkbox
              label={t('Künstler/Publizist (zählt für die Künstlersozialabgabe)')}
              checked={!!value.artist}
              disabled={moneyDisabled}
              onChange={(artist) => setValue((cur) => ({ ...cur, artist }))}
            />
          )}
        </fieldset>
      ) : null}
      {/* Ohne Webseite keine Nennung als Sponsor; eine gespeicherte Einwilligung bleibt sichtbar */}
      {(hasWebsite || !!value.website_consent) && (
        <fieldset disabled={disabled} className="subcard">
          <legend>{t('Webseite')}</legend>
          <Checkbox
            label={t('Darf auf unserer Webseite als Partner oder Sponsor genannt werden')}
            checked={!!value.website_consent}
            disabled={disabled}
            onChange={(website_consent) => setValue((cur) => ({ ...cur, website_consent }))}
          />
          {value.website_consent && (
            <Field
              label={t('Link auf der Webseite')}
              type="url"
              hint={t('Leer: die Webseite des Partners')}
              value={value.website_url ?? ''}
              onChange={(e) => setValue((cur) => ({ ...cur, website_url: e.target.value }))}
            />
          )}
          <p className="muted small">
            {t(
              'Die Einwilligung bitte schriftlich festhalten. Das Logo wählt ihr im Webseiten-Abschnitt „Partner und Sponsoren“.',
            )}
          </p>
        </fieldset>
      )}
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Notizen')}</legend>
        <TextArea
          label={t('Notizen')}
          value={value.notes ?? ''}
          onChange={(notes) => setValue((cur) => ({ ...cur, notes }))}
        />
        <Checkbox
          label={t('Aktiv')}
          checked={!!value.is_active}
          disabled={disabled}
          onChange={(is_active) => setValue((cur) => ({ ...cur, is_active }))}
        />
      </fieldset>
      <div className="button-row">
        {canEdit && !partner && (
          <button className="button button-primary" disabled={busy}>
            {t('Anlegen')}
          </button>
        )}
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() =>
            void confirmLeave().then((ok) => {
              if (ok) onClose()
            })
          }
        >
          {t('Schließen')}
        </button>
        {canEdit && partner && (
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={async () => {
              const yes = await confirmDialog({
                final: true,
                message: t(
                  'Geschäftspartner „{name}“ löschen? Das geht nur, solange er nirgends verwendet wird.',
                  { name: partner.name },
                ),
                confirmLabel: t('Löschen'),
              })
              if (!yes) return
              setError('')
              try {
                await partnerApi.remove(org.id, partner.id)
                onSaved()
              } catch (err) {
                setError(errorMessage(err))
              }
            }}
          >
            {t('Löschen')}
          </button>
        )}
      </div>
      {partner && <Contacts partner={partner} canEdit={canEdit} />}
      {partner && (
        <FieldsTab
          orgId={org.id}
          memberId={partner.id}
          canEdit={canEdit}
          load={partnerFieldApi.values}
          save={partnerFieldApi.saveValues}
          nested
        />
      )}
      {partner && <Agreements partner={partner} canEdit={canEdit} />}
      {partner && <PartnerDocuments partner={partner} canEdit={canEdit} />}
      {partner && financeOn && <TurnoverCard partner={partner} />}
      {canEdit && partner && others.length > 0 && (
        <details className="subcard">
          <summary>{t('Doppelten Eintrag zusammenführen')}</summary>
          <p className="muted small">
            {t(
              'Der gewählte Eintrag wird in diesen übernommen: Rechnungen, Buchungen, Vereinbarungen, Auftritte und Ansprechpartner wandern mit, der andere Eintrag wird gelöscht.',
            )}
          </p>
          <div className="button-row">
            <SelectField
              label={t('Doppelter Eintrag')}
              value={mergeWith}
              onChange={(e) => setMergeWith(e.target.value)}
            >
              <option value="">{t('bitte wählen')}</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.number} {o.name}
                </option>
              ))}
            </SelectField>
            <button
              type="button"
              className="button"
              disabled={!mergeWith || busy}
              onClick={async () => {
                const other = others.find((o) => o.id === Number(mergeWith))
                if (!other) return
                const yes = await confirmDialog({
                  final: true,
                  message: t('„{other}“ in „{name}“ übernehmen und danach löschen?', {
                    other: other.name,
                    name: partner.name,
                  }),
                  confirmLabel: t('Zusammenführen'),
                })
                if (!yes) return
                setBusy(true)
                setError('')
                try {
                  onSaved(await partnerApi.merge(org.id, partner.id, other.id))
                } catch (err) {
                  setError(errorMessage(err))
                } finally {
                  setBusy(false)
                }
              }}
            >
              {t('Zusammenführen')}
            </button>
          </div>
        </details>
      )}
    </form>
  )
}

function TurnoverCard({ partner }: { partner: BusinessPartner }) {
  const org = useActiveOrg()
  const data = useLoad(() => partnerApi.turnover(org.id, partner.id), [org.id, partner.id])
  if (data.error) return <Alert kind="error">{data.error}</Alert>
  if (!data.data) return null
  return (
    <section className="subcard stack">
      <h4>{t('Umsätze in der Kasse')}</h4>
      {data.data.years.length === 0 ? (
        <p className="muted small">{t('Noch keine Buchungen mit diesem Geschäftspartner.')}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('Geschäftsjahr')}</th>
                <th>{t('Einnahmen')}</th>
                <th>{t('Ausgaben')}</th>
                <th>{t('Buchungen')}</th>
              </tr>
            </thead>
            <tbody>
              {data.data.years.map((y) => (
                <tr key={y.year}>
                  <td>{y.year}</td>
                  <td>{formatEuro(Number(y.income))}</td>
                  <td>{formatEuro(Number(y.expense))}</td>
                  <td>{y.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.data.recent.length > 0 && (
        <Link to={`/finanzen/kassenbuch?partner=${encodeURIComponent(partner.name)}`}>
          {t('Buchungen im Kassenbuch zeigen')}
        </Link>
      )}
    </section>
  )
}
