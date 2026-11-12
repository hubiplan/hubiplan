// Geschäftspartner (Konzept geschaeftspartner.md, P1): Lieferanten, Dienstleister, Sponsoren,
// Behörden und andere außerhalb der Mitgliederliste, mit Ansprechpartnern.
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { financeApi } from '../../api/finance.ts'
import { PARTNER_KINDS, PARTNER_ROLES, partnerApi, partnerFieldApi } from '../../api/partners.ts'
import type {
  BusinessPartner,
  ContactInput,
  ImportResult,
  PartnerContact,
  PartnerInput,
  PartnerKind,
  PartnerRole,
} from '../../api/partners.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { FieldsTab } from '../members/FieldsTab.tsx'
import { FieldsAdmin } from '../settings/FieldsPage.tsx'
import { TextArea } from '../settings/TextArea.tsx'
import { Agreements } from './Agreements.tsx'
import { MailingCard } from './MailingCard.tsx'
import { PartnerDocuments } from './PartnerDocuments.tsx'
import { kindLabel, partnerAccess, roleLabel } from './access.ts'

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

export function PartnersPage() {
  const org = useActiveOrg()
  const access = partnerAccess(org.permissions)
  const load = useLoad(() => partnerApi.list(org.id), [org.id])
  const [selected, setSelected] = useState<BusinessPartner | 'new' | null>(null)
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('')
  const [role, setRole] = useState('')
  const [inactive, setInactive] = useState(false)
  const [importing, setImporting] = useState(false)
  const [mailing, setMailing] = useState(false)
  const [fields, setFields] = useState(false)
  const [error, setError] = useState('')
  const rows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    return (load.data ?? []).filter((p) => {
      if (!inactive && !p.is_active) return false
      if (kind && p.kind !== kind) return false
      if (role && !p.roles.includes(role as PartnerRole)) return false
      if (!needle) return true
      const hay = [
        p.name,
        p.number,
        p.details.city,
        p.details.email,
        ...p.contacts.map((c) => `${c.first_name} ${c.last_name}`),
      ]
      return hay.some((v) => (v ?? '').toLocaleLowerCase().includes(needle))
    })
  }, [load.data, search, kind, role, inactive])
  // Der Seitenkopf steht auch beim Laden und bei Fehlern (Seitenkopf-Rundgang)
  if (load.error || !load.data)
    return (
      <div className="stack">
        <PageHeader title={t('Geschäftspartner')} />
        {load.error ? <LoadError message={load.error} onRetry={load.reload} /> : <Loading />}
      </div>
    )
  const open = (value: BusinessPartner | 'new') =>
    void confirmLeave().then((ok) => {
      if (ok) setSelected(value)
    })
  return (
    <div className="stack">
      <PageHeader
        title={t('Geschäftspartner')}
        subtitle={t(
          'Lieferanten, Dienstleister, Sponsoren, Behörden und alle anderen außerhalb der Mitgliederliste.',
        )}
        primary={
          access.edit ? { label: t('Geschäftspartner anlegen'), onClick: () => open('new') } : null
        }
        actions={[
          {
            label: t('Als Excel exportieren'),
            onClick: () => {
              setError('')
              partnerApi
                .exportFile(org.id)
                .then((blob) => saveBlob(blob, 'geschaeftspartner.xlsx'))
                .catch((err: unknown) => setError(errorMessage(err)))
            },
          },
          access.edit && { label: t('Aus Excel importieren'), onClick: () => setImporting(true) },
          access.edit && { label: t('Serienbrief und Verteiler'), onClick: () => setMailing(true) },
          { label: t('Zusatzfelder'), onClick: () => setFields((x) => !x) },
        ]}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {mailing && <MailingCard onClose={() => setMailing(false)} />}
      {fields && (
        <div className="stack">
          <FieldsAdmin api={partnerFieldApi} editable={access.edit} partners />
          <div className="button-row">
            <button type="button" className="button" onClick={() => setFields(false)}>
              {t('Schließen')}
            </button>
          </div>
        </div>
      )}
      {importing && (
        <ImportCard
          onClose={(changed) => {
            setImporting(false)
            if (changed) void load.reload()
          }}
        />
      )}
      {org.modules.includes('finance') && org.permissions.includes('finance.edit') && (
        <SuggestionsCard onAdopted={() => void load.reload()} />
      )}
      {selected && (
        <PartnerForm
          key={selected === 'new' ? 'new' : selected.id}
          partner={selected === 'new' ? undefined : selected}
          others={load.data.filter((p) => selected === 'new' || p.id !== selected.id)}
          onSaved={(saved) => {
            void load.reload()
            setSelected(saved ?? null)
          }}
          onClose={() => setSelected(null)}
        />
      )}
      <div className="card stack">
        <div className="grid-4">
          <Field
            label={t('Suchen')}
            type="search"
            value={search}
            placeholder={t('Name, Nummer, Ort oder Ansprechpartner')}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SelectField label={t('Art')} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t('Alle')}</option>
            {PARTNER_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </SelectField>
          <SelectField label={t('Rolle')} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">{t('Alle')}</option>
            {PARTNER_ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </SelectField>
          <Checkbox label={t('Inaktive zeigen')} checked={inactive} onChange={setInactive} />
        </div>
        {rows.length === 0 ? (
          <p className="muted">
            {load.data.length === 0
              ? t('Noch keine Geschäftspartner vorhanden.')
              : t('Keine Treffer.')}
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('Nummer')}</th>
                  <th>{t('Name')}</th>
                  <th>{t('Art')}</th>
                  <th>{t('Rollen')}</th>
                  <th>{t('Ort')}</th>
                  <th>{t('Ansprechpartner')}</th>
                  <th>{t('Telefon')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const primary = p.contacts[0]
                  return (
                    <tr key={p.id}>
                      <td>{p.number}</td>
                      <td>
                        <button className="button button-ghost" onClick={() => open(p)}>
                          {p.name}
                        </button>
                        {!p.is_active && <span className="muted small"> · {t('Inaktiv')}</span>}
                      </td>
                      <td>{kindLabel(p.kind)}</td>
                      <td>{p.roles.map(roleLabel).join(', ') || '—'}</td>
                      <td>{p.details.city || '—'}</td>
                      <td>
                        {primary
                          ? `${primary.first_name} ${primary.last_name}`.trim()
                          : p.details.contact || '—'}
                      </td>
                      <td>{primary?.phone || p.details.phone || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function ImportCard({ onClose }: { onClose: (changed: boolean) => void }) {
  const org = useActiveOrg()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [probe, setProbe] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (dry: boolean) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await partnerApi.importFile(org.id, file, dry)
      if (dry) setProbe(result)
      else
        onClose(
          result.created + result.updated + result.contacts_created + result.contacts_updated > 0,
        )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      <h3>{t('Geschäftspartner aus Excel importieren')}</h3>
      <p className="muted small">
        {t(
          'Am einfachsten exportieren, in Excel ändern und wieder einlesen. Eine bekannte Nummer aktualisiert den Partner, leere Zellen ändern nichts. Zeilen ohne Nummer mit schon vorhandenem Namen werden übersprungen. Das Blatt „Ansprechpartner“ ergänzt und ändert Ansprechpartner.',
        )}
      </p>
      <input
        ref={input}
        type="file"
        accept=".xlsx"
        aria-label={t('Excel-Datei')}
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null)
          setProbe(null)
        }}
      />
      {probe && (
        <Alert kind={probe.errors.length ? 'error' : 'info'}>
          {t('{created} neu, {updated} geändert, {skipped} unverändert oder übersprungen.', {
            created: probe.created,
            updated: probe.updated,
            skipped: probe.skipped,
          })}{' '}
          {t('Ansprechpartner: {created} neu, {updated} geändert.', {
            created: probe.contacts_created,
            updated: probe.contacts_updated,
          })}
          {probe.errors.length > 0 && (
            <ul>
              {probe.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </Alert>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        {!probe ? (
          <button
            type="button"
            className="button button-primary"
            disabled={!file || busy}
            onClick={() => void run(true)}
          >
            {t('Datei prüfen')}
          </button>
        ) : (
          <button
            type="button"
            className="button button-primary"
            disabled={
              busy ||
              probe.created + probe.updated + probe.contacts_created + probe.contacts_updated === 0
            }
            onClick={() => void run(false)}
          >
            {t('Importieren')}
          </button>
        )}
        <button type="button" className="button" onClick={() => onClose(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </section>
  )
}

function PartnerForm({
  partner,
  others,
  onSaved,
  onClose,
}: {
  partner?: BusinessPartner
  others: BusinessPartner[]
  onSaved: (saved?: BusinessPartner) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const access = partnerAccess(org.permissions)
  const canEdit = access.edit
  const financeOn = org.modules.includes('finance') && org.permissions.includes('finance.view')
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
  useDraftGuard(canEdit && JSON.stringify(value) !== initial)
  const details = value.details!
  const setDetail = (key: keyof typeof details, v: string) =>
    setValue({ ...value, details: { ...details, [key]: v } })
  const setBank = (key: 'iban' | 'bic' | 'holder', v: string) =>
    setValue({ ...value, bank: { ...(value.bank ?? { iban: '', bic: '', holder: '' }), [key]: v } })
  const toggleRole = (r: PartnerRole, on: boolean) => {
    const roles = new Set(value.roles ?? [])
    if (on) roles.add(r)
    else roles.delete(r)
    setValue({ ...value, roles: PARTNER_ROLES.filter((x) => roles.has(x)) })
  }
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
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          const saved = await partnerApi.save(org.id, value, partner?.id)
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
      {error && <Alert kind="error">{error}</Alert>}
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Übersicht')}</legend>
        <div className="form-grid">
          <SelectField
            label={t('Art')}
            value={value.kind}
            onChange={(e) => setValue({ ...value, kind: e.target.value as PartnerKind })}
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
            onChange={(e) => setValue({ ...value, our_customer_number: e.target.value })}
          />
        </div>
        {value.kind === 'person' && (
          <p className="muted small">
            {t(
              'Privatpersonen nur für die Abwicklung von Verträgen speichern. Ist die Person Mitglied, bitte nicht doppelt anlegen.',
            )}
          </p>
        )}
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
            onChange={(e) => setValue({ ...value, first_contact_on: e.target.value || null })}
          />
          <Field
            label={t('Erstkontakt')}
            hint={t('Wie und wo, z. B. Schützenfest 2026')}
            maxLength={300}
            value={value.first_contact_note ?? ''}
            onChange={(e) => setValue({ ...value, first_contact_note: e.target.value })}
          />
          {canEdit ? (
            <MemberPicker
              orgId={org.id}
              label={t('Betreut von')}
              value={liaison}
              onChange={(m) => {
                setLiaison(m)
                setValue({ ...value, liaison: m?.id ?? null })
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
                setValue({
                  ...value,
                  default_category: e.target.value ? Number(e.target.value) : null,
                })
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
                setValue({
                  ...value,
                  payment_terms_days: e.target.value ? Number(e.target.value) : null,
                })
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
          <Checkbox
            label={t('Künstler/Publizist (zählt für die Künstlersozialabgabe)')}
            checked={!!value.artist}
            disabled={moneyDisabled}
            onChange={(artist) => setValue({ ...value, artist })}
          />
        </fieldset>
      ) : null}
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Webseite')}</legend>
        <Checkbox
          label={t('Darf auf unserer Webseite als Partner oder Sponsor genannt werden')}
          checked={!!value.website_consent}
          disabled={disabled}
          onChange={(website_consent) => setValue({ ...value, website_consent })}
        />
        {value.website_consent && (
          <Field
            label={t('Link auf der Webseite')}
            type="url"
            hint={t('Leer: die Webseite des Partners')}
            value={value.website_url ?? ''}
            onChange={(e) => setValue({ ...value, website_url: e.target.value })}
          />
        )}
        <p className="muted small">
          {t(
            'Die Einwilligung bitte schriftlich festhalten. Das Logo wählt ihr im Webseiten-Abschnitt „Partner und Sponsoren“.',
          )}
        </p>
      </fieldset>
      <fieldset disabled={disabled} className="subcard">
        <legend>{t('Notizen')}</legend>
        <TextArea
          label={t('Notizen')}
          value={value.notes ?? ''}
          onChange={(notes) => setValue({ ...value, notes })}
        />
        <Checkbox
          label={t('Aktiv')}
          checked={!!value.is_active}
          disabled={disabled}
          onChange={(is_active) => setValue({ ...value, is_active })}
        />
      </fieldset>
      <div className="button-row">
        {canEdit && (
          <button className="button button-primary" disabled={busy}>
            {t('Speichern')}
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

const emptyContact = (): ContactInput => ({
  last_name: '',
  first_name: '',
  function: '',
  email: '',
  phone: '',
  is_primary: false,
  receives_invoices: false,
  receives_mail: true,
  notes: '',
})

function Contacts({ partner, canEdit }: { partner: BusinessPartner; canEdit: boolean }) {
  const org = useActiveOrg()
  const [items, setItems] = useState<PartnerContact[]>(partner.contacts)
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<ContactInput>(emptyContact())
  const [error, setError] = useState('')
  const save = async () => {
    setError('')
    try {
      const saved = await partnerApi.saveContact(
        org.id,
        partner.id,
        draft,
        editing === 'new' ? undefined : (editing ?? undefined),
      )
      const rest = items
        .filter((c) => c.id !== saved.id)
        .map((c) => (saved.is_primary ? { ...c, is_primary: false } : c))
      setItems(saved.is_primary ? [saved, ...rest] : [...rest, saved])
      setEditing(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="subcard stack">
      <h4>{t('Ansprechpartner')}</h4>
      {items.length === 0 && <p className="muted small">{t('Noch keine Ansprechpartner.')}</p>}
      <ul className="item-list">
        {items.map((c) => (
          <li key={c.id} className="item-row">
            <div className="item-row-info">
              <strong>{`${c.first_name} ${c.last_name}`.trim()}</strong>
              {c.function && <span className="muted small"> · {c.function}</span>}
              {c.is_primary && <span className="muted small"> · {t('Hauptansprechpartner')}</span>}
              <div className="muted small">
                {[c.email, c.phone, c.receives_invoices ? t('erhält Rechnungen') : '']
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
            {canEdit && (
              <div className="button-row">
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setDraft({ ...c })
                    setEditing(c.id)
                  }}
                >
                  {t('Bearbeiten')}
                </button>
                <button
                  type="button"
                  className="button button-danger"
                  onClick={async () => {
                    if (!(await confirmDialog(t('Ansprechpartner entfernen?')))) return
                    try {
                      await partnerApi.removeContact(org.id, partner.id, c.id)
                      setItems(items.filter((x) => x.id !== c.id))
                    } catch (err) {
                      setError(errorMessage(err))
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {editing !== null && (
        <div className="stack">
          <div className="form-grid">
            <Field
              label={t('Vorname')}
              value={draft.first_name ?? ''}
              onChange={(e) => setDraft({ ...draft, first_name: e.target.value })}
            />
            <Field
              label={t('Name')}
              required
              value={draft.last_name ?? ''}
              onChange={(e) => setDraft({ ...draft, last_name: e.target.value })}
            />
            <Field
              label={t('Funktion')}
              value={draft.function ?? ''}
              onChange={(e) => setDraft({ ...draft, function: e.target.value })}
            />
            <Field
              label={t('E-Mail')}
              type="email"
              value={draft.email ?? ''}
              onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            />
            <Field
              label={t('Telefon')}
              type="tel"
              value={draft.phone ?? ''}
              onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
            />
            <Field
              label={t('Notiz')}
              value={draft.notes ?? ''}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </div>
          <Checkbox
            label={t('Hauptansprechpartner')}
            checked={!!draft.is_primary}
            onChange={(is_primary) => setDraft({ ...draft, is_primary })}
          />
          <Checkbox
            label={t('erhält Rechnungen')}
            checked={!!draft.receives_invoices}
            onChange={(receives_invoices) => setDraft({ ...draft, receives_invoices })}
          />
          <Checkbox
            label={t('erhält Post')}
            checked={!!draft.receives_mail}
            onChange={(receives_mail) => setDraft({ ...draft, receives_mail })}
          />
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={!draft.last_name?.trim()}
              onClick={() => void save()}
            >
              {t('Ansprechpartner speichern')}
            </button>
            <button type="button" className="button" onClick={() => setEditing(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {canEdit && editing === null && (
        <button
          type="button"
          className="button"
          onClick={() => {
            setDraft(emptyContact())
            setEditing('new')
          }}
        >
          {t('Ansprechpartner hinzufügen')}
        </button>
      )}
    </section>
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

function SuggestionsCard({ onAdopted }: { onAdopted: () => void }) {
  const org = useActiveOrg()
  const list = useLoad(() => partnerApi.suggestions(org.id), [org.id])
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  if (!list.data?.length) return null
  return (
    <details className="card">
      <summary>{t('Vorschläge aus dem Kassenbuch ({n})', { n: list.data.length })}</summary>
      <p className="muted small">
        {t(
          'Diese Namen stehen mehrfach als Empfänger oder Zahler im Kassenbuch. „Übernehmen“ legt einen Geschäftspartner an und verknüpft die Buchungen mit genau diesem Namen.',
        )}
      </p>
      {done && <Alert kind="success">{done}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <ul className="item-list">
        {list.data.map((s) => (
          <li key={s.name} className="item-row">
            <div className="item-row-info">
              <strong>{s.name}</strong>
              <div className="muted small">{t('{n}-mal verwendet', { n: s.count })}</div>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={async () => {
                  setError('')
                  try {
                    const created = await partnerApi.adopt(org.id, s.name)
                    setDone(
                      t('„{name}“ übernommen, {n} Buchungen verknüpft.', {
                        name: created.name,
                        n: created.linked,
                      }),
                    )
                    list.setData((list.data ?? []).filter((x) => x.name !== s.name))
                    onAdopted()
                  } catch (err) {
                    setError(errorMessage(err))
                  }
                }}
              >
                {t('Übernehmen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}
