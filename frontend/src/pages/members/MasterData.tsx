import { GENDERS, LEGAL_FORMS, memberApi } from '../../api/members.ts'
import type { Gender, MemberDetail } from '../../api/members.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { useAutoSave, useForm } from '../../components/forms.ts'
import { Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'
import { TitleField } from '../../components/TitleField.tsx'

export function MasterData({
  org,
  member,
  canEdit,
  onSaved,
}: {
  org: OrgSummary
  member: MemberDetail
  canEdit: boolean
  onSaved: (m: MemberDetail) => void
}) {
  const tm = useTerms()
  const c = member.contact
  const o = member.organization
  const organization = member.kind === 'organization'
  const form = useForm({
    last_name: member.last_name,
    first_name: member.first_name,
    birth_date: member.birth_date ?? '',
    gender: member.gender ?? '',
    title: member.title ?? '',
    name_suffix: o?.name_suffix ?? '',
    legal_form: o?.legal_form ?? '',
    legal_form_other: o?.legal_form_other ?? '',
    register: o?.register ?? '',
    vat_id: o?.vat_id ?? '',
    website: o?.website ?? '',
    size: o?.size != null ? String(o.size) : '',
    club_number: member.club_number,
    email: c?.email ?? '',
    phone: c?.phone ?? '',
    street: c?.street ?? '',
    postal_code: c?.postal_code ?? '',
    city: c?.city ?? '',
    country: c?.country ?? 'Deutschland',
  })
  const v = form.values
  const e = form.errors
  const auto = useAutoSave(
    form,
    // Nur Geändertes senden: Der Server ergänzt neue Kontaktdaten selbst, und so
    // überschreibt ein veralteter Stand keine gleichzeitige Änderung anderer Felder.
    (changes) => memberApi.update(org.id, member.id, changes),
    { enabled: canEdit, onSaved: (saved) => onSaved(saved as MemberDetail) },
  )

  return (
    <form
      className="card card-wide"
      aria-labelledby="stammdaten-titel"
      onSubmit={(ev) => ev.preventDefault()}
    >
      <h2 id="stammdaten-titel">{t('Stammdaten')}</h2>
      {canEdit && <SaveStatus auto={auto} />}
      <fieldset disabled={!canEdit}>
        {organization ? (
          <>
            <div className="grid-2">
              <Field
                label={t('Name der Organisation')}
                required
                value={v.last_name}
                error={e.last_name}
                onChange={(ev) => form.set('last_name', ev.target.value)}
              />
              <Field
                label={t('Namenszusatz')}
                value={v.name_suffix}
                error={e.name_suffix}
                onChange={(ev) => form.set('name_suffix', ev.target.value)}
              />
            </div>
            <div className="grid-4">
              <SelectField
                label={t('Rechtsform')}
                value={v.legal_form}
                error={e.legal_form}
                onChange={(ev) => form.set('legal_form', ev.target.value)}
              >
                <option value="">{t('– keine Angabe –')}</option>
                {LEGAL_FORMS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </SelectField>
              {v.legal_form === 'other' && (
                <Field
                  label={t('Rechtsform (Freitext)')}
                  value={v.legal_form_other}
                  error={e.legal_form_other}
                  onChange={(ev) => form.set('legal_form_other', ev.target.value)}
                />
              )}
              <Field
                label={t('Register (Gericht und Nummer)')}
                value={v.register}
                error={e.register}
                onChange={(ev) => form.set('register', ev.target.value)}
              />
              <Field
                label={t('USt-IdNr.')}
                value={v.vat_id}
                error={e.vat_id}
                onChange={(ev) => form.set('vat_id', ev.target.value)}
              />
            </div>
            <div className="grid-2">
              <Field
                label={t('Webseite')}
                value={v.website}
                error={e.website}
                onChange={(ev) => form.set('website', ev.target.value)}
              />
              <Field
                label={t('Größe')}
                hint={t('Für die Staffel nach Größe, zum Beispiel Mitarbeiter oder Einwohner')}
                type="number"
                min={0}
                value={v.size}
                error={e.size}
                onChange={(ev) => form.set('size', ev.target.value)}
              />
            </div>
          </>
        ) : (
          <div className="grid-4">
            <Field
              label={t('Name')}
              required
              value={v.last_name}
              error={e.last_name}
              onChange={(ev) => form.set('last_name', ev.target.value)}
            />
            <Field
              label={t('Vorname')}
              required
              value={v.first_name}
              error={e.first_name}
              onChange={(ev) => form.set('first_name', ev.target.value)}
            />
            {member.birth_year_only && member.birth_date && v.birth_date === member.birth_date ? (
              <Field
                label={t('Geburtsjahr')}
                value={member.birth_date.slice(0, 4)}
                hint={t('Nach der Löschfrist ist nur noch das Jahr gespeichert.')}
                readOnly
              />
            ) : (
              <Field
                label={t('Geburtsdatum')}
                type="date"
                value={v.birth_date}
                error={e.birth_date}
                onChange={(ev) => form.set('birth_date', ev.target.value)}
              />
            )}
            <SelectField
              label={t('Geschlecht')}
              value={v.gender}
              error={e.gender}
              onChange={(ev) => form.set('gender', ev.target.value as Gender)}
            >
              {GENDERS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </SelectField>
            <TitleField
              value={v.title}
              error={e.title}
              onChange={(value) => form.set('title', value)}
            />
          </div>
        )}
        <div className="grid-2">
          <Field
            label={t('E-Mail-Adresse (optional)')}
            type="email"
            value={v.email}
            error={e.email}
            onChange={(ev) => form.set('email', ev.target.value)}
          />
          <Field
            label={t('Telefon')}
            value={v.phone}
            error={e.phone}
            onChange={(ev) => form.set('phone', ev.target.value)}
          />
        </div>
        <Field
          label={t('Straße und Hausnummer')}
          required
          value={v.street}
          error={e.street}
          onChange={(ev) => form.set('street', ev.target.value)}
        />
        <div className="grid-3">
          <Field
            label={t('PLZ')}
            required
            value={v.postal_code}
            error={e.postal_code}
            onChange={(ev) => form.set('postal_code', ev.target.value)}
          />
          <Field
            label={t('Ort')}
            required
            value={v.city}
            error={e.city}
            onChange={(ev) => form.set('city', ev.target.value)}
          />
          <Field
            label={t('Land')}
            value={v.country}
            error={e.country}
            onChange={(ev) => form.set('country', ev.target.value)}
          />
        </div>
        <div className="grid-2">
          <Field
            label={t('Mitgliedsnummer {e_im}', { e_im: tm.e_im })}
            value={v.club_number}
            error={e.club_number}
            onChange={(ev) => form.set('club_number', ev.target.value)}
          />
        </div>
      </fieldset>
      <p className="muted small">
        {member.contact_shared
          ? t('Kontaktdaten werden für alle {e_pl} gemeinsam gepflegt.', { e_pl: tm.e_pl })
          : t('Kontaktdaten gelten nur für {name}.', { name: org.name })}
      </p>
    </form>
  )
}
