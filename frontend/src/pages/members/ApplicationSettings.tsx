// Mitglieder › Einrichtung › Online-Antrag: Formular, Zustimmungsregel, QR-Codes, Stand-Modus.
// Speichert automatisch wie die übrigen Einrichtungsseiten.
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { admissionApi } from '../../api/admission.ts'
import type {
  FieldKey,
  FieldState,
  FormSettings,
  KioskLinkRow,
  LangText,
} from '../../api/admission.ts'
import { availableLanguages } from '../../api/language.ts'
import type { LanguageOption } from '../../api/language.ts'
import { PERM } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import {
  errorMessage,
  formatDateTime,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import { Segmented } from '../../components/PageHeader.tsx'
import { Alert, Checkbox, Field, Loading, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

type Values = Omit<
  FormSettings,
  'choices' | 'form_url' | 'public_key' | 'rule_text' | 'statute_docs' | 'sepa_available'
>

const FIELD_LABELS: Record<Exclude<FieldKey, 'family'>, () => string> = {
  phone: () => t('Telefon'),
  gender: () => t('Geschlecht'),
  birth_date: () => t('Geburtsdatum'),
  unit: () => t('Untereinheit'),
  entry_wish: () => t('Gewünschter Eintritt'),
  note: () => t('Nachricht an den Verein'),
}

function useLanguages(): LanguageOption[] {
  const [langs, setLangs] = useState<LanguageOption[]>([{ code: 'de', name: 'Deutsch' }])
  useEffect(() => {
    let alive = true
    availableLanguages()
      .then((d) => alive && d.languages.length && setLangs(d.languages))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return langs
}

export function ApplicationSettings() {
  const org = useActiveOrg()
  const { data, error, setData } = useLoad(() => admissionApi.settings(org.id), [org.id])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <>
      <SettingsForm key={data.public_key} detail={data} onSaved={setData} />
      <DistributeCard detail={data} />
    </>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="stack-sm">
      <legend>{title}</legend>
      {children}
    </fieldset>
  )
}

function LangFields({
  label,
  value,
  onChange,
  long = false,
  hint,
}: {
  label: string
  value: LangText | undefined
  onChange: (v: LangText) => void
  long?: boolean
  hint?: string
}) {
  const langs = useLanguages()
  return (
    <>
      {langs.map((l) => {
        const text = langs.length > 1 ? `${label} (${l.name})` : label
        const id = `antrag-${label}-${l.code}`.replace(/\W+/g, '-')
        return long ? (
          <div key={l.code} className="field">
            <label className="field-label" htmlFor={id}>
              {text}
            </label>
            <textarea
              id={id}
              rows={4}
              maxLength={3000}
              value={value?.[l.code] ?? ''}
              onChange={(e) => onChange({ ...value, [l.code]: e.target.value })}
            />
            {hint && <small className="muted">{hint}</small>}
          </div>
        ) : (
          <Field
            key={l.code}
            label={text}
            value={value?.[l.code] ?? ''}
            maxLength={500}
            hint={hint}
            onChange={(e) => onChange({ ...value, [l.code]: e.target.value })}
          />
        )
      })}
    </>
  )
}

function Chips({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { id: number; name: string }[]
  value: number[]
  onChange: (v: number[]) => void
}) {
  return (
    <fieldset className="field">
      <legend>{label}</legend>
      <div className="chips">
        {options.map((o) => (
          <label key={o.id} className="checkbox chip">
            <input
              type="checkbox"
              checked={value.includes(o.id)}
              onChange={(e) =>
                onChange(e.target.checked ? [...value, o.id] : value.filter((x) => x !== o.id))
              }
            />
            <span>{o.name}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function SettingsForm({
  detail,
  onSaved,
}: {
  detail: FormSettings
  onSaved: (d: FormSettings) => void
}) {
  const org = useActiveOrg()
  const editable = org.permissions.includes(PERM.membersEdit)
  const initial: Values = {
    enabled: detail.enabled,
    types: detail.types,
    fields: detail.fields,
    custom_fields: detail.custom_fields,
    sepa: detail.sepa,
    confirm_statute: detail.confirm_statute,
    confirm_fee_rules: detail.confirm_fee_rules,
    consents: detail.consents,
    signature: detail.signature,
    texts: detail.texts,
    notify_roles: detail.notify_roles,
    rule: detail.rule,
    entry_date: detail.entry_date,
    purge_months: detail.purge_months,
    min_age: detail.min_age,
    minors: detail.minors,
  }
  const form = useForm<Values>(initial)
  const [ruleText, setRuleText] = useState(detail.rule_text)
  const auto = useAutoSave(form, (changes) => admissionApi.saveSettings(org.id, changes), {
    enabled: editable,
    onSaved: (saved) => {
      setRuleText((saved as FormSettings).rule_text)
      onSaved(saved as FormSettings)
    },
  })
  const { values: v, set, errors } = form
  const c = detail.choices
  const docs = detail.statute_docs
  const typeIds = v.types.map((x) => x.id)

  function toggleType(id: number, on: boolean) {
    const name = c.member_types.find((m) => m.id === id)?.name ?? ''
    set(
      'types',
      on
        ? [...v.types, { id, label: { de: name }, text: {}, organizations: false }]
        : v.types.filter((x) => x.id !== id),
    )
  }

  function patchType(id: number, change: Partial<Values['types'][number]>) {
    set(
      'types',
      v.types.map((x) => (x.id === id ? { ...x, ...change } : x)),
    )
  }

  const rule = v.rule
  const setRule = (change: Partial<typeof rule>) => set('rule', { ...rule, ...change })

  return (
    <form className="card card-wide stack" onSubmit={(e) => e.preventDefault()}>
      {editable && <SaveStatus auto={auto} />}
      <h2>{t('Online-Antrag')}</h2>
      <p className="muted small">
        {t(
          'Interessierte stellen den Mitgliedsantrag über einen Link oder QR-Code. Du prüfst ihn unter Mitglieder › Mitgliedsanträge und nimmst mit einem Klick auf.',
        )}
      </p>
      <fieldset disabled={!editable} className="stack">
        <Checkbox
          label={t('Online-Antrag einschalten')}
          checked={v.enabled}
          onChange={(on) => set('enabled', on)}
        />
        {v.enabled && v.types.length === 0 && (
          <Alert kind="info">{t('Bitte mindestens eine Mitgliedsart freigeben.')}</Alert>
        )}

        <Section title={t('Mitgliedsarten im Formular')}>
          {c.member_types.length === 0 && (
            <p className="muted">
              {t('Lege zuerst unter Einrichtung › Mitgliedsarten welche an.')}
            </p>
          )}
          {c.member_types.map((m) => {
            const entry = v.types.find((x) => x.id === m.id)
            return (
              <div key={m.id} className="stack-sm">
                <Checkbox
                  label={m.name}
                  checked={!!entry}
                  onChange={(on) => toggleType(m.id, on)}
                />
                {entry && (
                  <div className="stack-sm indent">
                    <LangFields
                      label={t('Bezeichnung im Formular')}
                      value={entry.label}
                      onChange={(label) => patchType(m.id, { label })}
                    />
                    <LangFields
                      label={t('Kurze Erklärung (freiwillig)')}
                      value={entry.text}
                      onChange={(text) => patchType(m.id, { text })}
                    />
                    <Checkbox
                      label={t('Auch Organisationen dürfen diese Art beantragen')}
                      checked={entry.organizations}
                      onChange={(organizations) => patchType(m.id, { organizations })}
                    />
                  </div>
                )}
              </div>
            )
          })}
          {errors.types && <p className="field-error">{errors.types}</p>}
          {typeIds.length > 0 && (
            <p className="muted small">
              {t('Der Jahresbeitrag erscheint, wenn unter Beiträge ein Satz für die Art steht.')}
            </p>
          )}
        </Section>

        <Section title={t('Felder')}>
          <p className="muted small">
            {t('Name, E-Mail-Adresse und Anschrift fragt das Formular immer ab.')}
          </p>
          {(Object.keys(FIELD_LABELS) as Exclude<FieldKey, 'family'>[]).map((k) => (
            <SelectField
              key={k}
              label={FIELD_LABELS[k]()}
              value={v.fields[k]}
              onChange={(e) => set('fields', { ...v.fields, [k]: e.target.value as FieldState })}
            >
              <option value="required">{t('Pflicht')}</option>
              <option value="optional">{t('freiwillig')}</option>
              <option value="off">{t('nicht abfragen')}</option>
            </SelectField>
          ))}
          <Checkbox
            label={t('Familienantrag: weitere Personen mit derselben Anschrift im selben Antrag')}
            checked={(v.fields.family ?? 'off') !== 'off'}
            onChange={(on) => set('fields', { ...v.fields, family: on ? 'optional' : 'off' })}
          />
          {c.custom_fields.length > 0 && (
            <Chips
              label={t('Zusatzfelder im Formular (freiwillig)')}
              options={c.custom_fields.map((x) => ({ id: x.id, name: x.label }))}
              value={v.custom_fields}
              onChange={(ids) => set('custom_fields', ids)}
            />
          )}
        </Section>

        <Section title={t('Beitrag und Lastschrift')}>
          {!detail.sepa_available && (
            <p className="muted small">
              {t('Lastschrift geht erst, wenn unter Beiträge die Gläubiger-ID eingetragen ist.')}
            </p>
          )}
          <SelectField
            label={t('SEPA-Lastschriftmandat im Antrag')}
            value={v.sepa}
            disabled={!detail.sepa_available}
            onChange={(e) => set('sepa', e.target.value as Values['sepa'])}
          >
            <option value="off">{t('nicht anbieten')}</option>
            <option value="offer">{t('anbieten (freiwillig)')}</option>
            <option value="required">{t('Pflicht')}</option>
          </SelectField>
          {v.sepa !== 'off' && v.signature === 'none' && (
            <Alert kind="info">
              {t(
                'Ohne Unterschrift erteilte Lastschriftmandate: Widerspricht ein Mitglied einer Lastschrift, kann die Bank ein unterschriebenes Mandat verlangen. Könnt ihr keines vorlegen, wird der Betrag bis zu 13 Monate lang zurückgebucht. Wer das nicht tragen möchte, stellt unten „Unterschrift nötig“ ein.',
              )}
            </Alert>
          )}
        </Section>

        <Section title={t('Bestätigungen und Einwilligungen')}>
          <Checkbox
            label={t('Satzung bestätigen lassen')}
            hint={
              docs.statute
                ? t('Fassung {x}', { x: docs.statute.version })
                : t('Unter Verein › Satzung ist noch keine hinterlegt.')
            }
            checked={v.confirm_statute}
            onChange={(on) => set('confirm_statute', on)}
          />
          <Checkbox
            label={t('Beitragsordnung bestätigen lassen')}
            hint={
              docs.fee_rules
                ? t('Fassung {x}', { x: docs.fee_rules.version })
                : t('Noch keine hinterlegt.')
            }
            checked={v.confirm_fee_rules}
            onChange={(on) => set('confirm_fee_rules', on)}
          />
          <p className="muted small">
            {t(
              'Die Datenschutzhinweise bestätigt jeder Antrag; den Text liefert die Datenschutzerklärung der Webseite.',
            )}
          </p>
          {c.consents.length > 0 && (
            <fieldset className="field">
              <legend>{t('Freiwillige Einwilligungen anbieten')}</legend>
              {c.consents.map((x) => (
                <Checkbox
                  key={x.key}
                  label={x.label}
                  checked={v.consents.includes(x.key)}
                  onChange={(on) =>
                    set(
                      'consents',
                      on ? [...v.consents, x.key] : v.consents.filter((k) => k !== x.key),
                    )
                  }
                />
              ))}
            </fieldset>
          )}
        </Section>

        <Section title={t('Unterschrift')}>
          <Segmented
            label={t('Unterschrift')}
            value={v.signature}
            onChange={(signature) => set('signature', signature)}
            options={[
              { value: 'none', label: t('Bestätigung per E-Mail genügt') },
              { value: 'required', label: t('Unterschrift nötig') },
            ]}
          />
          <p className="muted small">
            {v.signature === 'required'
              ? t(
                  'Unterschrieben wird auf dem Gerät oder auf dem ausgedruckten Antrag. Erst dann liegt der Antrag zur Entscheidung vor.',
                )
              : t(
                  'Die bestätigte E-Mail-Adresse gilt als Textform. Im Stand-Modus wird trotzdem auf dem Tablet unterschrieben, wenn du das hier einstellst.',
                )}
          </p>
        </Section>

        <Section title={t('Minderjährige')}>
          <Checkbox
            label={t('Minderjährige dürfen online beantragen (mit Erziehungsberechtigten)')}
            checked={v.minors}
            onChange={(on) => set('minors', on)}
          />
          <Field
            label={t('Mindestalter (leer = keins)')}
            type="number"
            min={0}
            max={99}
            value={v.min_age ?? ''}
            error={errors.min_age}
            onChange={(e) => set('min_age', e.target.value === '' ? null : Number(e.target.value))}
          />
        </Section>

        <Section title={t('Wer entscheidet?')}>
          <Segmented
            label={t('Wer entscheidet?')}
            value={rule.mode}
            onChange={(mode) => setRule({ mode })}
            options={[
              { value: 'single', label: t('eine Person') },
              { value: 'rule', label: t('Zustimmungen nach Satzung') },
              { value: 'assembly', label: t('die Versammlung') },
            ]}
          />
          {rule.mode === 'rule' && (
            <>
              <Chips
                label={t('Diese Rollen müssen zustimmen')}
                options={c.roles}
                value={rule.roles}
                onChange={(roles) => setRule({ roles })}
              />
              <Field
                label={t('Mindestzahl Zustimmungen (0 = keine)')}
                type="number"
                min={0}
                max={20}
                value={rule.min_count}
                onChange={(e) => setRule({ min_count: Number(e.target.value) || 0 })}
              />
              {rule.min_count > 0 && (
                <Chips
                  label={t(
                    'Die Mindestzahl kommt aus diesen Rollen (keine = alle mit Recht „Mitglieder bearbeiten“)',
                  )}
                  options={c.roles}
                  value={rule.pool}
                  onChange={(pool) => setRule({ pool })}
                />
              )}
              <Checkbox
                label={t('Die gewünschte Untereinheit muss zustimmen')}
                checked={rule.unit}
                onChange={(unit) => setRule({ unit })}
              />
              <Checkbox
                label={t('Eine Person darf mehrere geforderte Rollen abdecken')}
                checked={rule.multi_role}
                onChange={(multi_role) => setRule({ multi_role })}
              />
              <Checkbox
                label={t('Nach der letzten Zustimmung automatisch aufnehmen')}
                checked={rule.auto_admit}
                onChange={(auto_admit) => setRule({ auto_admit })}
              />
            </>
          )}
          {errors.rule && <p className="field-error">{errors.rule}</p>}
          <p className="small">{ruleText}</p>
          <Chips
            label={t('Neue Anträge melden an (leer = alle mit Recht „Mitglieder bearbeiten“)')}
            options={c.roles}
            value={v.notify_roles}
            onChange={(ids) => set('notify_roles', ids)}
          />
        </Section>

        <Section title={t('Eintritt und Aufbewahrung')}>
          <SelectField
            label={t('Eintrittsdatum')}
            value={v.entry_date}
            onChange={(e) => set('entry_date', e.target.value as Values['entry_date'])}
          >
            <option value="decision">{t('Tag der Aufnahme')}</option>
            <option value="next_month">{t('Erster des Folgemonats')}</option>
            <option value="wish">
              {t('Wunschtermin aus dem Antrag (sonst Tag der Aufnahme)')}
            </option>
          </SelectField>
          <Field
            label={t('Abgelehnte und zurückgezogene Anträge löschen nach (Monaten)')}
            type="number"
            min={1}
            max={36}
            value={v.purge_months}
            error={errors.purge_months}
            onChange={(e) => set('purge_months', Number(e.target.value) || 6)}
          />
        </Section>

        <Section title={t('Texte')}>
          <LangFields
            label={t('Einleitung über dem Formular')}
            long
            value={v.texts.intro}
            onChange={(intro) => set('texts', { ...v.texts, intro })}
          />
          <LangFields
            label={t('Dank nach dem Absenden')}
            long
            value={v.texts.thanks}
            onChange={(thanks) => set('texts', { ...v.texts, thanks })}
          />
          <LangFields
            label={t('Begrüßungsmail nach der Aufnahme')}
            long
            hint={t('Leer = kurzer Standardtext.')}
            value={v.texts.welcome}
            onChange={(welcome) => set('texts', { ...v.texts, welcome })}
          />
          <LangFields
            label={t('Absage per Mail')}
            long
            hint={t('Wird nur geschickt, wenn du es beim Ablehnen auswählst.')}
            value={v.texts.rejection}
            onChange={(rejection) => set('texts', { ...v.texts, rejection })}
          />
        </Section>
      </fieldset>
      {!editable && (
        <p className="muted small">{t('Du kannst diese Angaben ansehen, aber nicht ändern.')}</p>
      )}
    </form>
  )
}

/** Link, QR-Codes je Untereinheit und Stand-Modus */
function DistributeCard({ detail }: { detail: FormSettings }) {
  const org = useActiveOrg()
  const editable = org.permissions.includes(PERM.membersEdit)
  const [unit, setUnit] = useState('')
  const kiosk = useLoad(() => admissionApi.kioskLinks(org.id), [org.id])
  const [label, setLabel] = useState('')
  const [hours, setHours] = useState('8')
  const [created, setCreated] = useState<KioskLinkRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const url = unit ? `${detail.form_url}?einheit=${unit}` : detail.form_url

  async function create() {
    setBusy(true)
    setError(null)
    try {
      setCreated(await admissionApi.createKiosk(org.id, label, Number(hours) || 8))
      setLabel('')
      void kiosk.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function end(row: KioskLinkRow) {
    const ok = await confirmDialog({
      title: t('Stand-Link beenden?'),
      message: t('Auf dem Gerät mit „{x}“ geht danach kein Antrag mehr.', { x: row.label }),
      confirmLabel: t('Beenden'),
    })
    if (!ok) return
    try {
      await admissionApi.endKiosk(org.id, row.id)
      if (created?.id === row.id) setCreated(null)
      void kiosk.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (!detail.enabled) return null
  return (
    <div className="card card-wide stack-sm">
      <h2>{t('Formular verteilen')}</h2>
      {detail.choices.units.length > 0 && (
        <SelectField
          label={t('Für eine Untereinheit vorauswählen')}
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          hint={t('Der Link wählt die Untereinheit schon vor, z. B. für deren eigene Werbung.')}
        >
          <option value="">{t('keine')}</option>
          {detail.choices.units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </SelectField>
      )}
      <Field
        label={t('Adresse des Formulars')}
        value={url}
        readOnly
        onFocus={(e) => e.target.select()}
      />
      <div className="button-row">
        <button
          type="button"
          className="button"
          onClick={() => {
            void navigator.clipboard?.writeText(url).then(() => setCopied(true))
          }}
        >
          {copied ? t('Kopiert') : t('Adresse kopieren')}
        </button>
        <a
          className="button button-ghost"
          href={admissionApi.qrUrl(org.id, unit ? Number(unit) : undefined)}
          download={`mitglied-werden${unit ? `-${unit}` : ''}.svg`}
        >
          {t('QR-Code herunterladen')}
        </a>
        <a className="button button-ghost" href={url} target="_blank" rel="noreferrer">
          {t('Formular ansehen')}
        </a>
      </div>
      <img
        className="join-qr"
        src={admissionApi.qrUrl(org.id, unit ? Number(unit) : undefined)}
        alt={t('QR-Code zum Formular')}
        width={160}
        height={160}
      />

      <h3>{t('Stand-Modus')}</h3>
      <p className="muted small">
        {t(
          'Für ein Tablet am Vereinsstand: Antrag mit Unterschrift auf dem Gerät, ohne E-Mail-Bestätigung. Der Link gilt nur für die eingestellte Zeit; danach oder nach „Beenden“ ist das Gerät gesperrt.',
        )}
      </p>
      {kiosk.data && kiosk.data.length > 0 && (
        <ul className="item-list">
          {kiosk.data.map((k) => (
            <li key={k.id} className="item-row">
              <div className="item-row-info">
                <strong>{k.label}</strong>{' '}
                <span className="muted small">
                  {t('gültig bis {x}', { x: formatDateTime(k.valid_until) })}
                </span>
              </div>
              {editable && (
                <div className="button-row">
                  <button type="button" className="button button-ghost" onClick={() => void end(k)}>
                    {t('Beenden')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {created?.url && (
        <Alert kind="success" as="div">
          <p>{t('Öffne diese Adresse auf dem Tablet. Sie wird nur jetzt angezeigt.')}</p>
          <p className="break-all">{created.url}</p>
        </Alert>
      )}
      {editable && (
        <div className="grid-2">
          <Field
            label={t('Bezeichnung, z. B. Schützenfest')}
            value={label}
            maxLength={100}
            onChange={(e) => setLabel(e.target.value)}
          />
          <SelectField
            label={t('Gültig für')}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
          >
            <option value="4">{t('4 Stunden')}</option>
            <option value="8">{t('8 Stunden')}</option>
            <option value="24">{t('1 Tag')}</option>
            <option value="72">{t('3 Tage')}</option>
          </SelectField>
        </div>
      )}
      {editable && (
        <div className="button-row">
          <button
            type="button"
            className="button button-primary"
            disabled={busy || !label.trim()}
            onClick={() => void create()}
          >
            {t('Stand-Link anlegen')}
          </button>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
