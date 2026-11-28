// Beitrittsformular, Schritt 1: Angaben zur Person oder Organisation, Familie und Erziehungsberechtigte.
import { Segmented } from '../../components/PageHeader.tsx'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { FAMILY_LIMIT, newRelative, askAdult, label, type JoinModel } from './joinModel.ts'

export function JoinStepData({ m }: { m: JoinModel }) {
  const {
    s,
    f,
    kiosk,
    values,
    setValues,
    set,
    setRelative,
    setGuardian,
    err,
    type,
    discounts,
    person,
    minor,
    familyOn,
  } = m
  return (
    <>
      {s.types.length > 1 && (
        <fieldset className="stack-sm">
          <legend>{t('Mitgliedsart')}</legend>
          {s.types.map((x) => (
            <label key={x.id} className="checkbox">
              <input
                type="radio"
                name="member_type"
                checked={values.member_type === String(x.id)}
                onChange={() => {
                  set('member_type', String(x.id))
                  if (!x.organizations) set('kind', 'person')
                }}
              />
              <span>
                <strong>{x.label}</strong>
                {x.fee && <span className="muted"> · {t('{x} € im Jahr', { x: x.fee })}</span>}
                {x.text && <span className="muted small"> · {x.text}</span>}
              </span>
            </label>
          ))}
          {err('member_type') && <p className="field-error">{err('member_type')}</p>}
        </fieldset>
      )}
      {s.types.length === 1 && type && (
        <p>
          <strong>{type.label}</strong>
          {type.fee && <span className="muted"> · {t('{x} € im Jahr', { x: type.fee })}</span>}
        </p>
      )}
      {person && discounts.length > 0 && (
        <fieldset className="stack-sm">
          <legend>{t('Ermäßigter Beitrag')}</legend>
          <label className="checkbox">
            <input
              type="radio"
              name="discount"
              checked={!discounts.some((d) => String(d.id) === values.discount)}
              onChange={() => set('discount', '')}
            />
            <span>{t('keine Ermäßigung')}</span>
          </label>
          {discounts.map((d) => (
            <label key={d.id} className="checkbox">
              <input
                type="radio"
                name="discount"
                checked={values.discount === String(d.id)}
                onChange={() => set('discount', String(d.id))}
              />
              <span>
                <strong>{d.name}</strong>
                {d.kinds.length > 0 && (
                  <span className="muted small">
                    {' '}
                    · {t('Nachweis: {x}', { x: d.kinds.join(', ') })}
                  </span>
                )}
              </span>
            </label>
          ))}
          {values.discount && (
            <p className="muted small">
              {t(
                'Den Nachweis lädst du nach dem Absenden auf der Seite deines Antrags hoch (Link in der Bestätigungsmail) oder reichst ihn nach. Ohne Nachweis gilt der normale Beitrag.',
              )}
            </p>
          )}
          {err('discount') && <p className="field-error">{err('discount')}</p>}
        </fieldset>
      )}
      {type?.organizations && (
        <fieldset className="field">
          <legend>{t('Wer stellt den Antrag?')}</legend>
          <Segmented
            label={t('Wer stellt den Antrag?')}
            value={values.kind}
            onChange={(kind) => set('kind', kind)}
            options={[
              { value: 'person', label: t('eine Person') },
              { value: 'organization', label: t('eine Organisation (Firma, Verein)') },
            ]}
          />
        </fieldset>
      )}
      {person ? (
        <div className="grid-2">
          <Field
            label={t('Vorname')}
            value={values.first_name}
            autoComplete="given-name"
            onChange={(e) => set('first_name', e.target.value)}
            error={err('first_name')}
            required
          />
          <Field
            label={t('Nachname')}
            value={values.last_name}
            autoComplete="family-name"
            onChange={(e) => set('last_name', e.target.value)}
            error={err('last_name')}
            required
          />
        </div>
      ) : (
        <Field
          label={t('Name der Organisation')}
          value={values.last_name}
          autoComplete="organization"
          onChange={(e) => set('last_name', e.target.value)}
          error={err('last_name')}
          required
        />
      )}
      {person && f.birth_date !== 'off' && (
        <Field
          label={label(t('Geburtsdatum'), f.birth_date)}
          type="date"
          value={values.birth_date}
          autoComplete="bday"
          onChange={(e) => set('birth_date', e.target.value)}
          error={err('birth_date')}
          required={f.birth_date === 'required'}
        />
      )}
      {askAdult(f.birth_date, person, values.birth_date) && (
        <fieldset className={`field${err('adult') ? ' field-invalid' : ''}`}>
          <legend>{t('Bist du volljährig?')}</legend>
          <Segmented
            label={t('Bist du volljährig?')}
            value={values.adult}
            onChange={(adult) => set('adult', adult)}
            options={[
              { value: 'yes', label: t('Ja, 18 Jahre oder älter') },
              { value: 'no', label: t('Nein, unter 18 Jahre') },
            ]}
          />
          {err('adult') && <small className="field-error">{err('adult')}</small>}
        </fieldset>
      )}
      {person && f.gender !== 'off' && (
        <SelectField
          label={label(t('Geschlecht'), f.gender)}
          value={values.gender}
          onChange={(e) => set('gender', e.target.value)}
          error={err('gender')}
        >
          <option value="">{t('Keine Angabe')}</option>
          <option value="weiblich">{t('weiblich')}</option>
          <option value="männlich">{t('männlich')}</option>
          <option value="divers">{t('divers')}</option>
        </SelectField>
      )}
      <Field
        label={t('E-Mail-Adresse')}
        type="email"
        value={values.email}
        autoComplete="email"
        onChange={(e) => set('email', e.target.value)}
        error={err('email')}
        hint={
          kiosk
            ? t('Dorthin schickt der Verein die Entscheidung.')
            : t('Dorthin schicken wir den Link zum Bestätigen.')
        }
        required
      />
      {f.phone !== 'off' && (
        <Field
          label={label(t('Telefon'), f.phone)}
          type="tel"
          value={values.phone}
          autoComplete="tel"
          onChange={(e) => set('phone', e.target.value)}
          error={err('phone')}
        />
      )}
      <Field
        label={t('Straße und Hausnummer')}
        value={values.street}
        autoComplete="address-line1"
        onChange={(e) => set('street', e.target.value)}
        error={err('street')}
        required
      />
      <Field
        label={t('Adresszusatz (freiwillig)')}
        value={values.address_extra}
        autoComplete="address-line2"
        onChange={(e) => set('address_extra', e.target.value)}
        error={err('address_extra')}
      />
      <div className="grid-2">
        <Field
          label={t('PLZ')}
          value={values.postal_code}
          autoComplete="postal-code"
          inputMode="numeric"
          onChange={(e) => set('postal_code', e.target.value)}
          error={err('postal_code')}
          required
        />
        <Field
          label={t('Ort')}
          value={values.city}
          autoComplete="address-level2"
          onChange={(e) => set('city', e.target.value)}
          error={err('city')}
          required
        />
      </div>
      {minor && s.minors && (
        <fieldset className="stack-sm">
          <legend>{t('Erziehungsberechtigte')}</legend>
          <p className="muted small">
            {t(
              'Für Minderjährige stellen die Erziehungsberechtigten den Antrag. Die Bestätigung geht an die erste E-Mail-Adresse.',
            )}
          </p>
          {values.guardians.map((g, i) => (
            <div key={i} className="stack-sm">
              {i > 0 && <strong>{t('Zweiter Erziehungsberechtigter')}</strong>}
              <div className="grid-2">
                <Field
                  label={t('Vorname')}
                  value={g.first_name}
                  onChange={(e) => setGuardian(i, 'first_name', e.target.value)}
                />
                <Field
                  label={t('Nachname')}
                  value={g.last_name}
                  onChange={(e) => setGuardian(i, 'last_name', e.target.value)}
                />
              </div>
              <Field
                label={t('E-Mail-Adresse')}
                type="email"
                value={g.email}
                onChange={(e) => setGuardian(i, 'email', e.target.value)}
              />
              <Field
                label={t('Telefon (freiwillig)')}
                type="tel"
                value={g.phone ?? ''}
                onChange={(e) => setGuardian(i, 'phone', e.target.value)}
              />
            </div>
          ))}
          {err('guardians') && <p className="field-error">{err('guardians')}</p>}
          {values.guardians.length < 2 && (
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={() =>
                  set('guardians', [
                    ...values.guardians,
                    { last_name: '', first_name: '', email: '', phone: '' },
                  ])
                }
              >
                {t('Zweiten Erziehungsberechtigten angeben')}
              </button>
            </div>
          )}
        </fieldset>
      )}
      {familyOn && (
        <fieldset className="stack-sm">
          <legend>{t('Weitere Familienmitglieder')}</legend>
          <p className="muted small">
            {t(
              'Familienmitglieder mit derselben Anschrift kannst du hier gleich mit anmelden. Ihr bekommt Post und Beitragsrechnung gemeinsam.',
            )}
          </p>
          {values.family.map((r, i) => (
            <div
              key={i}
              className="stack-sm"
              role="group"
              aria-label={t('Familienmitglied {n}', { n: i + 1 })}
            >
              <div className="grid-2">
                <Field
                  label={t('Vorname')}
                  value={r.first_name}
                  required
                  onChange={(e) => setRelative(i, 'first_name', e.target.value)}
                />
                <Field
                  label={t('Nachname (wenn anders)')}
                  value={r.last_name}
                  placeholder={values.last_name}
                  onChange={(e) => setRelative(i, 'last_name', e.target.value)}
                />
              </div>
              {f.birth_date !== 'off' && (
                <Field
                  label={label(t('Geburtsdatum'), f.birth_date)}
                  type="date"
                  value={r.birth_date}
                  onChange={(e) => setRelative(i, 'birth_date', e.target.value)}
                />
              )}
              {s.types.length > 1 && (
                <SelectField
                  label={t('Mitgliedsart')}
                  value={r.member_type || values.member_type}
                  onChange={(e) => setRelative(i, 'member_type', e.target.value)}
                >
                  {s.types.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.label}
                    </option>
                  ))}
                </SelectField>
              )}
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() =>
                    set(
                      'family',
                      values.family.filter((_, n) => n !== i),
                    )
                  }
                >
                  {t('Entfernen')}
                </button>
              </div>
            </div>
          ))}
          {err('family') && <p className="field-error">{err('family')}</p>}
          {values.family.length < FAMILY_LIMIT && (
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={() => set('family', [...values.family, newRelative()])}
              >
                {t('Familienmitglied hinzufügen')}
              </button>
            </div>
          )}
        </fieldset>
      )}
      {f.unit !== 'off' && s.units.length > 0 && (
        <SelectField
          label={label(s.unit_label, f.unit)}
          value={values.unit}
          onChange={(e) => set('unit', e.target.value)}
          error={err('unit')}
        >
          <option value="">{t('Bitte wählen')}</option>
          {s.units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </SelectField>
      )}
      {f.entry_wish !== 'off' && (
        <Field
          label={label(t('Gewünschter Eintritt'), f.entry_wish)}
          type="date"
          value={values.entry_wish}
          onChange={(e) => set('entry_wish', e.target.value)}
          error={err('entry_wish')}
        />
      )}
      {s.custom_fields.map((c) => {
        const k = `custom_${c.id}`
        const v = values.custom[String(c.id)] ?? ''
        const change = (val: string) => {
          setValues((old) => ({ ...old, custom: { ...old.custom, [String(c.id)]: val } }))
        }
        if (c.type === 'choice')
          return (
            <SelectField
              key={c.id}
              label={t('{x} (freiwillig)', { x: c.label })}
              value={v}
              hint={c.help || undefined}
              error={err(k)}
              onChange={(e) => change(e.target.value)}
            >
              <option value="">{t('Keine Angabe')}</option>
              {c.choices.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </SelectField>
          )
        if (c.type === 'bool')
          return (
            <Checkbox
              key={c.id}
              label={c.label}
              hint={c.help || undefined}
              checked={v === 'true'}
              onChange={(on) => change(on ? 'true' : '')}
            />
          )
        return (
          <Field
            key={c.id}
            label={t('{x} (freiwillig)', { x: c.label })}
            type={c.type === 'date' ? 'date' : c.type === 'number' ? 'number' : 'text'}
            value={v}
            hint={c.help || undefined}
            error={err(k)}
            onChange={(e) => change(e.target.value)}
          />
        )
      })}
      {f.note !== 'off' && (
        <div className="field">
          <label className="field-label" htmlFor="join-note">
            {label(t('Nachricht an den Verein'), f.note)}
          </label>
          <textarea
            id="join-note"
            rows={3}
            maxLength={2000}
            value={values.note}
            onChange={(e) => set('note', e.target.value)}
          />
          {err('note') && <p className="field-error">{err('note')}</p>}
        </div>
      )}
      {/* Honigtopf: für Menschen unsichtbar */}
      <div className="sr-only" aria-hidden="true">
        <label>
          {t('Webseite')}
          <input
            tabIndex={-1}
            autoComplete="off"
            value={values.homepage}
            onChange={(e) => set('homepage', e.target.value)}
          />
        </label>
      </div>
    </>
  )
}
