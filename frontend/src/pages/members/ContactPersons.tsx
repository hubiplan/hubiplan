import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { GENDERS, memberApi } from '../../api/members.ts'
import type { ContactPerson, ContactPersonInput, Gender, MemberRow } from '../../api/members.ts'
import { ApiError } from '../../api/client.ts'
import { errorMessage, formatDate } from '../../components/forms.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { Segmented } from '../../components/PageHeader.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

type Flags = Pick<
  ContactPerson,
  'is_primary' | 'receives_mail' | 'receives_invoices' | 'represents' | 'member_access'
>

const FLAGS: { key: keyof Flags; label: string }[] = [
  { key: 'is_primary', label: t('Hauptansprechpartner') },
  { key: 'receives_mail', label: t('erhält Rundschreiben') },
  { key: 'receives_invoices', label: t('erhält Rechnungen') },
  { key: 'represents', label: t('vertritt in Versammlungen') },
  { key: 'member_access', label: t('Mitgliederzugang') },
]

/** Ansprechpartner eines Organisationsmitglieds (Abschnitt in der Mitgliedsakte). */
export function ContactPersons({
  orgId,
  memberId,
  contacts,
  canEdit,
  onChange,
}: {
  orgId: number
  memberId: number
  contacts: ContactPerson[]
  canEdit: boolean
  onChange: () => void
}) {
  const [editing, setEditing] = useState<ContactPerson | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function remove(c: ContactPerson) {
    const ok = await confirmDialog({
      title: t('{name} als Ansprechpartner entfernen?', { name: c.display_name }),
      message: t(
        'Name und Kontaktdaten des Ansprechpartners werden gelöscht. In Rechnungen und Protokollen bleibt der Name stehen.',
      ),
      confirmLabel: t('Entfernen'),
    })
    if (!ok) return
    try {
      await memberApi.deleteContact(orgId, memberId, c.id)
      setError(null)
      onChange()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section className="card card-wide" aria-labelledby="ansprechpartner-titel">
      <h2 id="ansprechpartner-titel">{t('Ansprechpartner')}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      {contacts.length === 0 ? (
        <p className="muted">{t('Noch kein Ansprechpartner eingetragen.')}</p>
      ) : (
        <ul className="plain-list stack">
          {contacts.map((c) =>
            editing !== 'new' && editing?.id === c.id ? (
              <li key={c.id}>
                <ContactForm
                  orgId={orgId}
                  memberId={memberId}
                  contact={c}
                  onDone={(changed) => {
                    setEditing(null)
                    if (changed) onChange()
                  }}
                />
              </li>
            ) : (
              <li key={c.id}>
                <strong>
                  {c.linked_member ? (
                    <Link to={`/mitglieder/${c.linked_member}`}>{c.display_name}</Link>
                  ) : (
                    c.display_name
                  )}
                </strong>
                {c.function && ` · ${c.function}`}
                {c.is_primary && (
                  <span className="badge" style={{ marginLeft: '0.5rem' }}>
                    {t('Hauptansprechpartner')}
                  </span>
                )}
                <br />
                <span className="muted small">
                  {[
                    c.contact_email,
                    c.contact_phone,
                    c.since && t('seit {date}', { date: formatDate(c.since) }),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                <br />
                <span className="muted small">
                  {FLAGS.filter((f) => f.key !== 'is_primary' && c[f.key])
                    .map((f) => f.label)
                    .join(', ') || t('keine Aufgaben')}
                </span>
                {canEdit && (
                  <span className="actions">
                    {' '}
                    <button type="button" className="link-button" onClick={() => setEditing(c)}>
                      {t('Bearbeiten')}
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => void remove(c)}>
                      {t('Entfernen')}
                    </button>
                  </span>
                )}
              </li>
            ),
          )}
        </ul>
      )}
      {canEdit &&
        (editing === 'new' ? (
          <ContactForm
            orgId={orgId}
            memberId={memberId}
            contact={null}
            first={contacts.length === 0}
            onDone={(changed) => {
              setEditing(null)
              if (changed) onChange()
            }}
          />
        ) : (
          <p>
            <button type="button" className="button" onClick={() => setEditing('new')}>
              {t('Ansprechpartner hinzufügen')}
            </button>
          </p>
        ))}
    </section>
  )
}

function ContactForm({
  orgId,
  memberId,
  contact,
  first = false,
  onDone,
}: {
  orgId: number
  memberId: number
  contact: ContactPerson | null
  first?: boolean
  onDone: (changed: boolean) => void
}) {
  const linkedAtStart = contact?.linked_member ?? null
  const [linked, setLinked] = useState<boolean>(contact ? linkedAtStart !== null : false)
  const [picked, setPicked] = useState<MemberRow | null>(null)
  const [v, setV] = useState({
    last_name: contact?.last_name ?? '',
    first_name: contact?.first_name ?? '',
    gender: (contact?.gender ?? '') as Gender,
    function: contact?.function ?? '',
    email: contact?.email ?? '',
    phone: contact?.phone ?? '',
    since: contact?.since ?? '',
    is_primary: contact?.is_primary ?? first,
    receives_mail: contact?.receives_mail ?? true,
    receives_invoices: contact?.receives_invoices ?? true,
    represents: contact?.represents ?? true,
    member_access: contact?.member_access ?? false,
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof typeof v>(key: K, value: (typeof v)[K]) =>
    setV((old) => ({ ...old, [key]: value }))

  async function save(ev: FormEvent) {
    ev.preventDefault()
    const data: ContactPersonInput = {
      function: v.function,
      since: v.since || null,
      is_primary: v.is_primary,
      receives_mail: v.receives_mail,
      receives_invoices: v.receives_invoices,
      represents: v.represents,
    }
    if (linked) {
      const member = picked?.id ?? linkedAtStart
      if (!member) {
        setErrors({ member: t('Bitte ein Mitglied auswählen.') })
        return
      }
      data.member = member
    } else {
      Object.assign(data, {
        member: null,
        last_name: v.last_name,
        first_name: v.first_name,
        gender: v.gender,
        email: v.email,
        phone: v.phone,
      })
    }
    setBusy(true)
    try {
      if (contact) await memberApi.updateContact(orgId, memberId, contact.id, data)
      else await memberApi.addContact(orgId, memberId, data)
      onDone(true)
    } catch (err) {
      setErrors(
        err instanceof ApiError && Object.keys(err.fieldErrors).length > 0
          ? err.fieldErrors
          : { detail: errorMessage(err) },
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={(ev) => void save(ev)}>
      {(errors.detail || errors.non_field_errors) && (
        <Alert kind="error">{errors.detail || errors.non_field_errors}</Alert>
      )}
      <fieldset disabled={busy} className="stack">
        <fieldset>
          <legend>{t('Art des Ansprechpartners')}</legend>
          <Segmented
            label={t('Art des Ansprechpartners')}
            value={linked ? 'linked' : 'name'}
            onChange={(kind) => setLinked(kind === 'linked')}
            options={[
              { value: 'name', label: t('Name eingeben') },
              { value: 'linked', label: t('Mitglied auswählen') },
            ]}
          />
        </fieldset>
        {linked ? (
          <>
            {linkedAtStart && !picked && contact ? (
              <p>
                {t('Verknüpft mit {name}.', { name: contact.display_name })}{' '}
                {t('Name und Kontakt kommen aus der Akte des Mitglieds.')}
              </p>
            ) : (
              <MemberPicker
                orgId={orgId}
                value={picked}
                onChange={setPicked}
                label={t('Mitglied')}
                search={(term) =>
                  memberApi
                    .list(orgId, { suche: term, status: 'aktiv', typ: 'person', page_size: 8 })
                    .then((page) => page.results)
                }
              />
            )}
            {errors.member && <p className="field-error">{errors.member}</p>}
          </>
        ) : (
          <>
            <div className="grid-3">
              <Field
                label={t('Name')}
                required
                value={v.last_name}
                error={errors.last_name}
                onChange={(ev) => set('last_name', ev.target.value)}
              />
              <Field
                label={t('Vorname')}
                value={v.first_name}
                error={errors.first_name}
                onChange={(ev) => set('first_name', ev.target.value)}
              />
              <SelectField
                label={t('Geschlecht')}
                value={v.gender}
                error={errors.gender}
                onChange={(ev) => set('gender', ev.target.value as Gender)}
              >
                {GENDERS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </SelectField>
            </div>
            <div className="grid-2">
              <Field
                label={t('E-Mail-Adresse')}
                type="email"
                value={v.email}
                error={errors.email}
                onChange={(ev) => set('email', ev.target.value)}
              />
              <Field
                label={t('Telefon')}
                value={v.phone}
                error={errors.phone}
                onChange={(ev) => set('phone', ev.target.value)}
              />
            </div>
          </>
        )}
        <div className="grid-2">
          <Field
            label={t('Funktion')}
            hint={t('z. B. Geschäftsführer, Bürgermeister')}
            value={v.function}
            error={errors.function}
            onChange={(ev) => set('function', ev.target.value)}
          />
          <Field
            label={t('Ansprechpartner seit')}
            type="date"
            value={v.since}
            error={errors.since}
            onChange={(ev) => set('since', ev.target.value)}
          />
        </div>
        {FLAGS.filter((f) => f.key !== 'member_access').map((f) => (
          <Checkbox
            key={f.key}
            label={f.label}
            checked={v[f.key]}
            onChange={(value) => set(f.key, value)}
          />
        ))}
        <p className="muted small">
          {t(
            'Den Mitgliederzugang richtet ihr je Ansprechpartner im Reiter „Rollen und Konto“ ein.',
          )}
        </p>
        <div className="actions">
          <button type="submit">{t('Speichern')}</button>{' '}
          <button type="button" className="link-button" onClick={() => onDone(false)}>
            {t('Abbrechen')}
          </button>
        </div>
      </fieldset>
    </form>
  )
}
