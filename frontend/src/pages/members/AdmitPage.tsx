import { useId, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { newRequestKey } from '../../api/client.ts'
import { GENDERS, LEGAL_FORMS, memberApi, memberName, todayIso } from '../../api/members.ts'
import type { Duplicate, Gender, MemberKind } from '../../api/members.ts'
import { orgApi, unitName } from '../../api/orgs.ts'
import { errorMessage, formatDate, useForm, useLoad } from '../../components/forms.ts'
import { useChangesGuard } from '../../components/leaveGuard.ts'
import { Alert, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { PageHeader, Segmented } from '../../components/PageHeader.tsx'
import { t } from '../../i18n/index.ts'

type Step = 'person' | 'details'

export function AdmitPage() {
  const org = useActiveOrg()
  const terms = useTerms()
  const fed = !!terms.dv_has
  const navigate = useNavigate()
  const types = useLoad(() => memberApi.types(org.id), [org.id])
  const departments = useLoad(() => orgApi.departmentChoices(org.id), [org.id])
  const [step, setStep] = useState<Step>('person')
  const previousStep = useRef(step)
  const personForm = useRef<HTMLFormElement>(null)
  const stepHeading = useRef<HTMLHeadingElement>(null)
  const unitErrorId = useId()
  useLayoutEffect(() => {
    if (previousStep.current === step) return
    previousStep.current = step
    if (step === 'person')
      personForm.current?.querySelector<HTMLInputElement>('input:not([type="radio"])')?.focus()
    else stepHeading.current?.focus()
  }, [step])
  const [duplicates, setDuplicates] = useState<Duplicate[]>([])
  const [linked, setLinked] = useState<Duplicate | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [transferSent, setTransferSent] = useState(false)

  // Ein Schlüssel je Aufnahme: erneutes Absenden legt die Person nicht doppelt an
  const [requestKey] = useState(newRequestKey)
  const form = useForm({
    kind: 'person' as MemberKind,
    last_name: '',
    name_suffix: '',
    legal_form: '',
    legal_form_other: '',
    register: '',
    vat_id: '',
    website: '',
    size: '',
    first_name: '',
    birth_date: '',
    gender: '' as Gender,
    email: '',
    phone: '',
    street: '',
    postal_code: '',
    city: '',
    country: 'Deutschland',
    club_number: '',
    member_type: '',
    entry_date: todayIso(),
    department_ids: [] as number[],
  })
  const v = form.values
  const e = form.errors
  const organization = v.kind === 'organization'
  const summary = organization
    ? [v.last_name, v.name_suffix].filter(Boolean).join(' – ')
    : [`${v.last_name}, ${v.first_name}`, v.birth_date && formatDate(v.birth_date)]
        .filter(Boolean)
        .join(' · ')
  // Eingaben vor dem Absenden nicht unbemerkt verlieren (UX-Audit 31.10. W01)
  const [done, setDone] = useState(false)
  useChangesGuard(v, !done && !transferSent)

  async function checkPerson(ev: FormEvent) {
    ev.preventDefault()
    setChecking(true)
    setCheckError(null)
    try {
      const found = organization
        ? await memberApi.organizationDuplicates(org.id, v.last_name)
        : await memberApi.duplicates(org.id, v.last_name, v.first_name, v.birth_date)
      setDuplicates(found)
      setLinked(null)
      setStep('details')
    } catch (err) {
      setCheckError(errorMessage(err))
    } finally {
      setChecking(false)
    }
  }

  async function save(ev: FormEvent) {
    ev.preventDefault()
    const payload: Record<string, unknown> = {
      ...v,
      member_type: Number(v.member_type),
      person: linked?.id ?? null,
    }
    const created = await form.submit(
      () => memberApi.admit(org.id, payload, requestKey),
      t('Aufgenommen.'),
    )
    if (created) {
      setDone(true)
      navigate(`/mitglieder/${(created as { id: number }).id}`)
    }
  }

  async function requestTransfer() {
    if (!linked) return
    const sent = await form.submit(
      () =>
        memberApi.createTransfer(org.id, {
          person: linked.id,
          last_name: v.last_name,
          first_name: v.first_name,
          birth_date: v.birth_date,
          member_type: Number(v.member_type),
          entry_date: v.entry_date,
          club_number: v.club_number,
          department_ids: v.department_ids,
          email: v.email,
          phone: v.phone,
          street: v.street,
          postal_code: v.postal_code,
          city: v.city,
          country: v.country,
        }),
      t('Wechselanfrage gestellt. Sobald {e_der_andere} zustimmt, wird die Aufnahme gespeichert.', {
        e_der_andere: terms.e_der_andere,
      }),
    )
    if (sent) setTransferSent(true)
  }

  const activeConflict =
    !!linked && !!e.member_type && e.member_type.includes('bereits aktives Mitglied')
  const activeTypes = types.data?.filter((tm) => !tm.is_archived) ?? []
  const selectedType = activeTypes.find((tm) => String(tm.id) === v.member_type)

  return (
    <section>
      <PageHeader name={t('Mitglied aufnehmen')} />

      {types.error && (
        <Alert kind="error">
          {t(
            'Die Mitgliedsarten konnten nicht geladen werden. {error} Deine Eingaben bleiben erhalten.',
            { error: types.error },
          )}{' '}
          <button type="button" className="link-button" onClick={() => void types.reload()}>
            {t('Erneut laden')}
          </button>
        </Alert>
      )}
      {departments.error && (
        <LoadError
          message={t(
            'Untereinheiten konnten nicht geladen werden. Deine Eingaben bleiben erhalten.',
          )}
          onRetry={() => void departments.reload()}
        />
      )}
      {types.data && activeTypes.length === 0 && (
        <Alert kind="error">
          {t('Für die Aufnahme fehlt noch eine Mitgliedsart. Lege zuerst unter')}{' '}
          <Link to="/mitglieder/einrichtung/mitgliedsarten">
            {t('Mitglieder → Einrichtung → Mitgliedsarten')}
          </Link>{' '}
          {t('mindestens eine an.')}
        </Alert>
      )}

      {step === 'person' ? (
        <form ref={personForm} className="card card-wide" onSubmit={checkPerson}>
          <h2>{organization ? t('1. Organisation') : t('1. Person')}</h2>
          <fieldset className="field">
            <legend>{t('Mitglied ist')}</legend>
            <Segmented
              label={t('Mitglied ist')}
              value={organization ? 'organization' : 'person'}
              onChange={(kind) => form.set('kind', kind)}
              options={[
                { value: 'person', label: t('eine Person') },
                { value: 'organization', label: t('eine Organisation (Firma, Verein, Behörde …)') },
              ]}
            />
          </fieldset>
          <p className="muted small">
            {organization
              ? t('Zuerst prüfen wir, ob es die Organisation schon gibt.')
              : fed
                ? t(
                    'Zuerst prüfen wir, ob es die Person schon gibt – zum Beispiel als Mitglied {e_eines_anderen} {dv_im}.',
                    { e_eines_anderen: terms.e_eines_anderen, dv_im: terms.dv_im },
                  )
                : t('Zuerst prüfen wir, ob es die Person schon gibt.')}
          </p>
          {organization ? (
            <>
              <div className="grid-2">
                <Field
                  label={t('Name der Organisation')}
                  required
                  value={v.last_name}
                  onChange={(ev) => form.set('last_name', ev.target.value)}
                />
                <Field
                  label={t('Namenszusatz (optional)')}
                  hint={t('Zum Beispiel Niederlassung oder Abteilung')}
                  value={v.name_suffix}
                  onChange={(ev) => form.set('name_suffix', ev.target.value)}
                />
              </div>
              <div className="grid-2">
                <SelectField
                  label={t('Rechtsform (optional)')}
                  value={v.legal_form}
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
                    onChange={(ev) => form.set('legal_form_other', ev.target.value)}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="grid-4">
              <Field
                label={t('Name')}
                required
                value={v.last_name}
                onChange={(ev) => form.set('last_name', ev.target.value)}
              />
              <Field
                label={t('Vorname')}
                required
                value={v.first_name}
                onChange={(ev) => form.set('first_name', ev.target.value)}
              />
              <Field
                label={t('Geburtsdatum')}
                type="date"
                hint={t(
                  'Freiwillig. Ohne Geburtsdatum sucht HUBIplan nur unter den eigenen Mitgliedern nach gleichem Namen.',
                )}
                value={v.birth_date}
                onChange={(ev) => form.set('birth_date', ev.target.value)}
              />
              <SelectField
                label={t('Geschlecht')}
                value={v.gender}
                onChange={(ev) => form.set('gender', ev.target.value as Gender)}
              >
                {GENDERS.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </SelectField>
            </div>
          )}
          {checkError && <Alert kind="error">{checkError}</Alert>}
          <button type="submit" className="button button-primary" disabled={checking}>
            {t('Weiter')}
          </button>
        </form>
      ) : (
        <form className="stack" onSubmit={save}>
          {duplicates.length > 0 && (
            <div className="card card-wide">
              <h2 ref={stepHeading} tabIndex={-1}>
                {t('Mögliche Treffer')}
              </h2>
              <p className="muted small">
                {organization
                  ? t('Ist eine dieser Organisationen gemeint? Dann wird sie verknüpft.')
                  : fed
                    ? t(
                        'Ist eine dieser Personen gemeint? Dann wird sie verknüpft: Verbandsnummer und Eintritt in {dv_akk} bleiben erhalten.',
                        { dv_akk: terms.dv_akk },
                      )
                    : t('Ist eine dieser Personen gemeint? Dann wird sie verknüpft.')}
              </p>
              <ul className="duplicates">
                {duplicates.map((d) => (
                  <li key={d.id}>
                    <label className="checkbox">
                      <input
                        type="radio"
                        name="duplicate"
                        disabled={d.already_member_here}
                        checked={linked?.id === d.id}
                        onChange={() => setLinked(d)}
                      />
                      <span>
                        <strong>{memberName(d)}</strong>
                        {d.birth_date && ` · ${formatDate(d.birth_date)}`}
                        {d.member_number &&
                          t(' · Verbandsnr. {member_number}', { member_number: d.member_number })}
                        {d.clubs &&
                          d.clubs.length > 0 &&
                          t(' · Mitglied in: {x}', { x: d.clubs.join(', ') })}
                        {d.already_member_here &&
                          t(' · ist oder war schon Mitglied hier (Wiedereintritt in der Akte)')}
                      </span>
                    </label>
                  </li>
                ))}
                <li>
                  <label className="checkbox">
                    <input
                      type="radio"
                      name="duplicate"
                      checked={linked === null}
                      onChange={() => setLinked(null)}
                    />
                    <span>
                      {organization
                        ? t('Keine davon – neue Organisation anlegen')
                        : t('Keine davon – neue Person anlegen')}
                    </span>
                  </label>
                </li>
              </ul>
            </div>
          )}

          <div className="card card-wide">
            <h2 ref={duplicates.length === 0 ? stepHeading : undefined} tabIndex={-1}>
              {t('2. Mitgliedschaft und Kontakt')}
            </h2>
            <p className="muted small">
              {summary}{' '}
              <button type="button" className="link-button" onClick={() => setStep('person')}>
                {t('ändern')}
              </button>
            </p>
            <div className="grid-3">
              <SelectField
                label={t('Mitgliedsart')}
                required
                value={v.member_type}
                error={e.member_type}
                onChange={(ev) => form.set('member_type', ev.target.value)}
              >
                <option value="">{t('– bitte wählen –')}</option>
                {activeTypes.map((tm) => (
                  <option key={tm.id} value={tm.id}>
                    {tm.name}
                  </option>
                ))}
              </SelectField>
              <Field
                label={t('Eintritt')}
                type="date"
                required
                value={v.entry_date}
                error={e.entry_date}
                onChange={(ev) => form.set('entry_date', ev.target.value)}
              />
              <Field
                label={t('Mitgliedsnummer {e_im} (optional)', { e_im: terms.e_im })}
                value={v.club_number}
                hint={t('Leer lassen, dann vergibt HUBIplan die nächste freie Nummer.')}
                error={e.club_number}
                onChange={(ev) => form.set('club_number', ev.target.value)}
              />
            </div>
            {selectedType && (
              <p className="muted small">
                {selectedType.active ? t('aktiv') : t('nicht aktiv')}
                {fed &&
                  (selectedType.reported
                    ? t(' · wird an {dv_akk} gemeldet', { dv_akk: terms.dv_akk })
                    : t(' · wird nicht gemeldet'))}
              </p>
            )}
            {departments.data && departments.data.length > 0 && (
              <fieldset
                className="field"
                tabIndex={e.department_ids ? -1 : undefined}
                aria-describedby={e.department_ids ? unitErrorId : undefined}
                aria-invalid={!!e.department_ids}
              >
                <legend>{t('{units} (optional)', { units: terms.Pl })}</legend>
                <div className="chips">
                  {departments.data
                    .filter((d) => d.is_active)
                    .map((d) => (
                      <label key={d.id} className="checkbox chip">
                        <input
                          type="checkbox"
                          checked={v.department_ids.includes(d.id)}
                          onChange={(ev) =>
                            form.set(
                              'department_ids',
                              ev.target.checked
                                ? [...v.department_ids, d.id]
                                : v.department_ids.filter((x) => x !== d.id),
                            )
                          }
                        />
                        <span>{unitName(d)}</span>
                      </label>
                    ))}
                </div>
                {e.department_ids && (
                  <small id={unitErrorId} className="field-error">
                    {e.department_ids}
                  </small>
                )}
              </fieldset>
            )}
          </div>

          {organization && (
            <div className="card card-wide">
              <h3>{t('Angaben zur Organisation (optional)')}</h3>
              <div className="grid-3">
                <Field
                  label={t('Register (Gericht und Nummer)')}
                  hint={t('Zum Beispiel Amtsgericht Musterstadt HRB 12345')}
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
            </div>
          )}

          <div className="card card-wide">
            <h3>
              {organization
                ? t('Anschrift und Kontakt der Organisation')
                : t('Kontakt und Anschrift')}
            </h3>
            <div className="grid-2">
              <Field
                label={t('E-Mail-Adresse (optional)')}
                type="email"
                hint={t(
                  'Ohne E-Mail erhält das Mitglied Schreiben per Brief. Ein Online-Zugang kann später eingerichtet werden.',
                )}
                value={v.email}
                error={e.email}
                onChange={(ev) => form.set('email', ev.target.value)}
              />
              <Field
                label={t('Telefon (optional)')}
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
          </div>

          {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
          {e.person && <Alert kind="error">{e.person}</Alert>}
          {activeConflict && !transferSent && (
            <div className="card card-wide">
              <p>
                {t('Ihr könnt {e_beim_anderen} eine', { e_beim_anderen: terms.e_beim_anderen })}{' '}
                <strong>{t('Wechselanfrage')}</strong>{' '}
                {t(
                  'stellen. Dort bestätigt man dann den Austritt oder den Wechsel zu einer nicht aktiven Art.',
                )}
              </p>
              <button
                type="button"
                className="button button-primary"
                onClick={() => void requestTransfer()}
              >
                {t('Wechselanfrage stellen')}
              </button>
            </div>
          )}
          {transferSent && (
            <Link to="/mitglieder/anfragen" className="button button-ghost">
              {t('Zu den Wechselanfragen')}
            </Link>
          )}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={form.busy}>
              {t('Aufnehmen')}
            </button>
            <Link to="/mitglieder" className="button button-ghost">
              {t('Abbrechen')}
            </Link>
          </div>
        </form>
      )}
    </section>
  )
}
