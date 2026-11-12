// Öffentlicher Mitgliedsantrag (konzepte/online-beitrittsformular.md B1–B5).
// Drei Schritte: Angaben · Beitrag und Zahlung · Bestätigen. Im Stand-Modus (Tablet am
// Vereinsstand) mit Unterschrift auf dem Gerät und ohne E-Mail-Bestätigung.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import type { SignatureInput } from '../../api/finance.ts'
import { ApiError } from '../../api/client.ts'
import { joinApi, solveChallenge } from '../../api/admission.ts'
import type {
  FamilyMember,
  FieldState,
  Guardian,
  JoinSchema,
  JoinSubmission,
} from '../../api/admission.ts'
import { SignaturePad } from '../../components/SignaturePad.tsx'
import { errorMessage } from '../../components/forms.ts'
import { Logo } from '../../components/Logo.tsx'
import { Segmented } from '../../components/PageHeader.tsx'
import { Alert, Checkbox, Field, Loading, SelectField } from '../../components/ui.tsx'
import { lang, t } from '../../i18n/index.ts'
import { LanguageSwitch } from '../../i18n/LanguageControls.tsx'

type Step = 0 | 1 | 2

interface Values {
  kind: 'person' | 'organization'
  member_type: string
  last_name: string
  first_name: string
  birth_date: string
  adult: '' | 'yes' | 'no'
  gender: string
  email: string
  phone: string
  street: string
  address_extra: string
  postal_code: string
  city: string
  country: string
  unit: string
  entry_wish: string
  note: string
  custom: Record<string, string>
  pay: boolean
  holder: string
  iban: string
  bic: string
  confirmations: string[]
  consents: string[]
  guardians: Guardian[]
  family: FamilyMember[]
  homepage: string
}

const empty: Values = {
  kind: 'person',
  member_type: '',
  last_name: '',
  first_name: '',
  birth_date: '',
  adult: '',
  gender: '',
  email: '',
  phone: '',
  street: '',
  address_extra: '',
  postal_code: '',
  city: '',
  country: '',
  unit: '',
  entry_wish: '',
  note: '',
  custom: {},
  pay: false,
  holder: '',
  iban: '',
  bic: '',
  confirmations: [],
  consents: [],
  guardians: [{ last_name: '', first_name: '', email: '', phone: '' }],
  family: [],
  homepage: '',
}

const FAMILY_LIMIT = 8
const newRelative = (): FamilyMember => ({
  first_name: '',
  last_name: '',
  birth_date: '',
  member_type: '',
})

/** In welchem Schritt steht das Feld? (für Fehler vom Server) */
function stepOf(key: string): Step {
  if (key === 'mandate') return 1
  if (key === 'confirmations' || key === 'consents' || key === 'signature') return 2
  return 0
}

/** Fehlerschlüssel einer Bestätigung (Ankreuzfeld) */
function confirmKey(key: string): string {
  return 'confirm_' + key
}

function ageOn(birth: string, today = new Date()): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(birth)
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  let age = today.getFullYear() - y
  if (today.getMonth() + 1 < mo || (today.getMonth() + 1 === mo && today.getDate() < d)) age--
  return age
}

const label = (base: string, state: FieldState) =>
  state === 'optional' ? t('{x} (freiwillig)', { x: base }) : base

/** /mitglied-werden/:key (online) und /mitglied-werden/stand/:token (Stand-Modus) */
export function JoinFormPage({ kiosk = false }: { kiosk?: boolean }) {
  const params = useParams()
  const [search] = useSearchParams()
  const key = (kiosk ? params.token : params.key) ?? ''
  const unitHint = search.get('einheit') ?? ''
  // Link „Mitarbeiter melden“ einer Firma (Haushalte und Firmen H5)
  const companyToken = kiosk ? '' : (search.get('firma') ?? '')
  const preset = useRef({
    first_name: search.get('vorname') ?? '',
    last_name: search.get('name') ?? '',
    email: search.get('mail') ?? '',
  })
  const [schema, setSchema] = useState<JoinSchema | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [values, setValues] = useState<Values>(empty)
  const [step, setStep] = useState<Step>(0)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [signature, setSignature] = useState<SignatureInput | null>(null)
  const [padKey, setPadKey] = useState(0)
  const [done, setDone] = useState<{ number?: string } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  // Rechenaufgabe schon im Hintergrund lösen, während jemand ausfüllt
  const solved = useRef<Promise<number> | null>(null)

  useEffect(() => {
    let alive = true
    const load = kiosk
      ? joinApi.kiosk(key, lang())
      : joinApi.form(key, lang(), unitHint, companyToken)
    load
      .then((d) => {
        if (!alive) return
        setSchema(d)
        const given = d.company ? preset.current : null
        setValues((v) => ({
          ...v,
          first_name: v.first_name || given?.first_name || '',
          last_name: v.last_name || given?.last_name || '',
          email: v.email || given?.email || '',
          member_type: v.member_type || (d.types.length === 1 ? String(d.types[0].id) : ''),
          unit: v.unit || (d.unit ? String(d.unit) : ''),
          pay: v.pay || d.sepa === 'required',
        }))
        if (d.challenge) {
          const c = d.challenge
          solved.current = solveChallenge(c.salt, c.difficulty)
          solved.current.catch(() => undefined)
        }
      })
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status === 404) setInvalid(true)
        else setLoadError(errorMessage(err))
      })
    return () => {
      alive = false
    }
  }, [key, kiosk, unitHint, companyToken, attempt])

  useEffect(() => {
    heading.current?.focus()
  }, [step, done])

  const type = schema?.types.find((x) => String(x.id) === values.member_type) ?? null
  const person = values.kind === 'person'
  const age = ageOn(values.birth_date)
  const minor = useMemo(() => {
    if (!schema || !person) return false
    if (schema.fields.birth_date !== 'off' && values.birth_date) return age !== null && age < 18
    return values.adult === 'no'
  }, [schema, person, values.birth_date, values.adult, age])

  function set<K extends keyof Values>(k: K, v: Values[K]) {
    setValues((old) => ({ ...old, [k]: v }))
    setErrors((old) => {
      if (!(k in old)) return old
      const next = { ...old }
      delete next[k as string]
      return next
    })
  }

  function toggle(k: 'confirmations' | 'consents', item: string, on: boolean) {
    setValues((old) => ({
      ...old,
      [k]: on ? [...new Set([...old[k], item])] : old[k].filter((x) => x !== item),
    }))
  }

  function setRelative(i: number, k: keyof FamilyMember, v: string) {
    setValues((old) => ({
      ...old,
      family: old.family.map((g, n) => (n === i ? { ...g, [k]: v } : g)),
    }))
  }

  function setGuardian(i: number, k: keyof Guardian, v: string) {
    setValues((old) => ({
      ...old,
      guardians: old.guardians.map((g, n) => (n === i ? { ...g, [k]: v } : g)),
    }))
  }

  if (!schema) {
    return (
      <main className="login-page">
        <div className="card public-photo stack-sm">
          <h1>{t('Mitglied werden')}</h1>
          {invalid && (
            <Alert kind="error">
              {kiosk
                ? t('Dieser Stand-Link ist abgelaufen oder beendet.')
                : t('Dieses Antragsformular gibt es nicht oder es ist gerade abgeschaltet.')}
            </Alert>
          )}
          {loadError && (
            <>
              <Alert kind="error">{loadError}</Alert>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => {
                    setLoadError(null)
                    setAttempt((n) => n + 1)
                  }}
                >
                  {t('Erneut versuchen')}
                </button>
              </div>
            </>
          )}
          {!invalid && !loadError && <Loading />}
        </div>
      </main>
    )
  }

  const s = schema
  const f = s.fields
  // Familienantrag (Haushalte H6): ältere Server kennen das Feld nicht
  const familyOn = person && !minor && (f.family ?? 'off') !== 'off'
  const confirmations = [
    ...s.confirmations,
    ...(minor
      ? [
          {
            key: 'guardian',
            label: t(
              'Ich bin erziehungsberechtigt und stimme dem Antrag zu (bei zwei Erziehungsberechtigten mit Einverständnis des anderen).',
            ),
          },
        ]
      : []),
    ...(values.pay && s.sepa !== 'off'
      ? [{ key: 'mandate', label: t('Ich erteile das SEPA-Mandat.') }]
      : []),
  ]

  /** Prüfung im Browser, damit niemand erst am Ende Fehler aus Schritt 1 sieht */
  function check(which: Step): Record<string, string> {
    const e: Record<string, string> = {}
    const need = t('Pflichtfeld.')
    if (which === 0) {
      if (!values.member_type) e.member_type = t('Bitte eine Mitgliedsart wählen.')
      if (!values.last_name.trim()) e.last_name = need
      if (person && !values.first_name.trim()) e.first_name = need
      if (!/^\S+@\S+\.\S+$/.test(values.email.trim()))
        e.email = t('Bitte eine gültige E-Mail-Adresse angeben.')
      for (const k of ['street', 'postal_code', 'city'] as const) if (!values[k].trim()) e[k] = need
      if (f.phone === 'required' && !values.phone.trim()) e.phone = need
      if (person && f.gender === 'required' && !values.gender) e.gender = need
      if (person && f.birth_date === 'required' && !values.birth_date) e.birth_date = need
      if (person && f.birth_date === 'off' && !values.adult)
        e.adult = t('Bitte angeben, ob du volljährig bist.')
      if (person && age !== null && s.min_age && age < s.min_age)
        e.birth_date = t('Eine Mitgliedschaft ist erst ab {age} Jahren möglich.', {
          age: s.min_age,
        })
      if (minor && !s.minors) e.birth_date = t('Online können nur Volljährige beantragen.')
      if (minor) {
        const g = values.guardians[0]
        if (!g.last_name.trim() || !g.first_name.trim() || !/^\S+@\S+\.\S+$/.test(g.email.trim()))
          e.guardians = t('Bitte Name und E-Mail-Adresse eines Erziehungsberechtigten angeben.')
      }
      if (f.unit === 'required' && !values.unit) e.unit = need
      if (f.entry_wish === 'required' && !values.entry_wish) e.entry_wish = need
      if (f.note === 'required' && !values.note.trim()) e.note = need
    }
    if (which === 1 && values.pay && s.sepa !== 'off') {
      if (!values.holder.trim()) e.holder = need
      if (!values.iban.trim()) e.iban = need
    }
    if (which === 2) {
      for (const c of confirmations)
        if (!values.confirmations.includes(c.key)) e[confirmKey(c.key)] = t('Bitte bestätigen.')
      if (kiosk && s.signature === 'required' && !signature)
        e.signature = t('Bitte unterschreiben.')
    }
    return e
  }

  function next(e: React.FormEvent) {
    e.preventDefault()
    const found = check(step)
    setErrors(found)
    setError(null)
    if (Object.keys(found).length) {
      setError(t('Bitte die markierten Angaben prüfen.'))
      return
    }
    if (step < 2) setStep((step + 1) as Step)
    else void submit()
  }

  async function submit() {
    setBusy(true)
    setError(null)
    const data: JoinSubmission = {
      language: lang(),
      kind: values.kind,
      member_type: Number(values.member_type),
      last_name: values.last_name,
      first_name: person ? values.first_name : '',
      email: values.email,
      street: values.street,
      address_extra: values.address_extra,
      postal_code: values.postal_code,
      city: values.city,
      country: values.country,
      phone: values.phone,
      gender: person ? values.gender : '',
      birth_date: person && values.birth_date ? values.birth_date : undefined,
      adult: person && f.birth_date === 'off' ? values.adult === 'yes' : null,
      unit: values.unit ? Number(values.unit) : null,
      entry_wish: values.entry_wish || undefined,
      note: values.note,
      custom: values.custom,
      mandate:
        values.pay && s.sepa !== 'off'
          ? { holder: values.holder, iban: values.iban, bic: values.bic }
          : null,
      confirmations: values.confirmations.filter((k) => confirmations.some((c) => c.key === k)),
      consents: values.consents,
      guardians: minor ? values.guardians.filter((g) => g.last_name || g.email) : [],
      family: familyOn
        ? values.family
            .filter((r) => r.first_name.trim())
            .map((r) => ({
              first_name: r.first_name.trim(),
              last_name: r.last_name.trim(),
              birth_date: f.birth_date !== 'off' && r.birth_date ? r.birth_date : undefined,
              member_type: r.member_type ? Number(r.member_type) : undefined,
            }))
        : [],
      signature,
      homepage: values.homepage,
      ...(s.company && companyToken ? { company: companyToken } : {}),
    }
    try {
      if (kiosk) {
        const res = await joinApi.kioskSubmit(key, data)
        setDone({ number: res.number })
      } else {
        const nonce = await (solved.current ??
          solveChallenge(s.challenge?.salt ?? '', s.challenge?.difficulty ?? 0))
        await joinApi.submit(key, { ...data, challenge: s.challenge?.token, nonce })
        setDone({})
      }
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) {
        const found: Record<string, string> = {}
        for (const [k, v] of Object.entries(err.fieldErrors)) {
          if (k === 'confirmations') {
            for (const c of confirmations) found[confirmKey(c.key)] = t('Bitte bestätigen.')
          } else found[k] = v
        }
        setErrors(found)
        const first = Math.min(...Object.keys(err.fieldErrors).map(stepOf)) as Step
        setStep(first)
      }
      if (err instanceof ApiError && err.body && (err.body as { code?: string }).code) {
        // Rechenaufgabe abgelaufen: neu laden, Eingaben bleiben
        setAttempt((n) => n + 1)
      }
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function again() {
    setValues({ ...empty, pay: s.sepa === 'required' })
    setSignature(null)
    setPadKey((n) => n + 1)
    setErrors({})
    setError(null)
    setStep(0)
    setDone(null)
  }

  if (done) {
    return (
      <main className="login-page">
        <div className="card public-photo stack-sm">
          <h1 ref={heading} tabIndex={-1}>
            {t('Vielen Dank!')}
          </h1>
          {kiosk ? (
            <>
              <Alert kind="success">
                {t('Der Antrag {number} ist eingegangen. Der Verein meldet sich per E-Mail.', {
                  number: done.number ?? '',
                })}
              </Alert>
              <div className="button-row">
                <button type="button" className="button button-primary" onClick={again}>
                  {t('Nächster Antrag')}
                </button>
              </div>
            </>
          ) : (
            <>
              <Alert kind="success">
                {t(
                  'Fast geschafft: Wir haben dir eine E-Mail geschickt. Bitte bestätige den Antrag über den Link darin innerhalb von 48 Stunden.',
                )}
              </Alert>
              {minor && (
                <p>
                  {t(
                    'Die E-Mail ging an den Erziehungsberechtigten. Erst mit dessen Bestätigung ist der Antrag gestellt.',
                  )}
                </p>
              )}
              {s.thanks && <p className="rsvp-public-text">{s.thanks}</p>}
            </>
          )}
        </div>
      </main>
    )
  }

  const steps = [t('Angaben'), t('Beitrag und Zahlung'), t('Bestätigen')]
  const err = (k: string) => errors[k]

  return (
    <main className="login-page">
      <form className="card public-photo stack-sm join-form" onSubmit={next} noValidate>
        <div className="login-logo">
          <Logo name={s.organization} logoUrl={null} />
        </div>
        <h1 ref={heading} tabIndex={-1}>
          {t('Mitglied werden')} · {s.organization}
        </h1>
        {kiosk && s.kiosk && <p className="muted small">{t('Stand: {x}', { x: s.kiosk })}</p>}
        <ol className="join-steps" aria-label={t('Schritte')}>
          {steps.map((name, i) => (
            <li key={name} aria-current={i === step ? 'step' : undefined}>
              {name}
            </li>
          ))}
        </ol>
        {step === 0 && s.intro && <p className="rsvp-public-text">{s.intro}</p>}
        {s.company && (
          <p className="alert alert-info">
            {t('Den Mitgliedsbeitrag zahlt {x}.', { x: s.company })}
          </p>
        )}

        {step === 0 && (
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
                      {x.fee && (
                        <span className="muted"> · {t('{x} € im Jahr', { x: x.fee })}</span>
                      )}
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
                {type.fee && (
                  <span className="muted"> · {t('{x} € im Jahr', { x: type.fee })}</span>
                )}
              </p>
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
            {person && f.birth_date === 'off' && (
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
        )}

        {step === 1 && (
          <>
            {type && (
              <p>
                {t('Mitgliedsart: {x}', { x: type.label })}
                {type.fee
                  ? ` · ${t('Beitrag: {x} € im Jahr', { x: type.fee })}`
                  : ` · ${t('Den Beitrag nennt dir der Verein.')}`}
              </p>
            )}
            {s.company && (
              <p className="muted">
                {t(
                  'Beitrag zahlt {x}. Eine Lastschrift ist nur nötig, wenn du selbst zahlen möchtest.',
                  { x: s.company },
                )}
              </p>
            )}
            {s.sepa === 'off' && !s.company && (
              <p className="muted">
                {t('Wie der Beitrag gezahlt wird, erfährst du nach der Aufnahme.')}
              </p>
            )}
            {s.sepa === 'offer' && (
              <Checkbox
                label={t('Beitrag per Lastschrift zahlen')}
                checked={values.pay}
                onChange={(on) => set('pay', on)}
              />
            )}
            {values.pay && s.sepa !== 'off' && (
              <fieldset className="stack-sm">
                <legend>{t('SEPA-Lastschriftmandat')}</legend>
                {s.mandate.text && <p className="small rsvp-public-text">{s.mandate.text}</p>}
                {s.mandate.creditor_id && (
                  <p className="small muted">
                    {t('Gläubiger-ID: {x}', { x: s.mandate.creditor_id })} ·{' '}
                    {t('Die Mandatsreferenz erhältst du nach der Aufnahme.')}
                  </p>
                )}
                <Field
                  label={t('Kontoinhaber')}
                  value={values.holder}
                  autoComplete="name"
                  onChange={(e) => set('holder', e.target.value)}
                  error={err('holder')}
                  required
                />
                <Field
                  label={t('IBAN')}
                  value={values.iban}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(e) => set('iban', e.target.value.toUpperCase())}
                  error={err('iban') || err('mandate')}
                  required
                />
                <Field
                  label={t('BIC (freiwillig)')}
                  value={values.bic}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(e) => set('bic', e.target.value.toUpperCase())}
                />
              </fieldset>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <fieldset className="stack-sm">
              <legend>{t('Bestätigungen')}</legend>
              {confirmations.map((c) => (
                <div key={c.key}>
                  <Checkbox
                    label={c.label}
                    checked={values.confirmations.includes(c.key)}
                    onChange={(on) => toggle('confirmations', c.key, on)}
                    hint={
                      'version' in c && c.version ? t('Fassung {x}', { x: c.version }) : undefined
                    }
                  />
                  {'url' in c && c.url && (
                    <a href={c.url} target="_blank" rel="noreferrer" className="small">
                      {t('Dokument öffnen')}
                    </a>
                  )}
                  {'text' in c && c.text && (
                    <details className="small">
                      <summary>{t('Text lesen')}</summary>
                      <p className="rsvp-public-text">{c.text}</p>
                    </details>
                  )}
                  {err(confirmKey(c.key)) && (
                    <p className="field-error">{err(confirmKey(c.key))}</p>
                  )}
                </div>
              ))}
            </fieldset>
            {s.consents.length > 0 && (
              <fieldset className="stack-sm">
                <legend>{t('Einwilligungen (freiwillig)')}</legend>
                <p className="muted small">
                  {t('Du kannst sie jederzeit beim Verein widerrufen.')}
                </p>
                {s.consents.map((c) => (
                  <Checkbox
                    key={c.key}
                    label={c.label}
                    checked={values.consents.includes(c.key)}
                    onChange={(on) => toggle('consents', c.key, on)}
                  />
                ))}
              </fieldset>
            )}
            {s.signature === 'required' && (
              <fieldset className="stack-sm">
                <legend>{t('Unterschrift')}</legend>
                <p className="muted small">
                  {kiosk
                    ? t('Bitte hier mit dem Finger oder Stift unterschreiben.')
                    : t(
                        'Der Verein braucht eine Unterschrift. Du kannst hier unterschreiben oder später den Antrag als PDF ausdrucken und unterschrieben abgeben.',
                      )}
                </p>
                <SignaturePad key={padKey} onChange={setSignature} />
                {err('signature') && <p className="field-error">{err('signature')}</p>}
              </fieldset>
            )}
          </>
        )}

        {error && <Alert kind="error">{error}</Alert>}
        <div className="button-row">
          {step > 0 && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => setStep((step - 1) as Step)}
            >
              {t('Zurück')}
            </button>
          )}
          <button type="submit" className="button button-primary" disabled={busy}>
            {step < 2 ? t('Weiter') : busy ? t('Wird gesendet …') : t('Antrag absenden')}
          </button>
        </div>
        {!kiosk && <LanguageSwitch />}
      </form>
    </main>
  )
}
