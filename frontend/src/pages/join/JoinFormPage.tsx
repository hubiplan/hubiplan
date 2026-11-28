// Öffentlicher Mitgliedsantrag (konzepte/online-beitrittsformular.md B1–B5).
// Drei Schritte: Angaben · Beitrag und Zahlung · Bestätigen. Im Stand-Modus (Tablet am
// Vereinsstand) mit Unterschrift auf dem Gerät und ohne E-Mail-Bestätigung.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import type { SignatureInput } from '../../api/finance.ts'
import { ApiError } from '../../api/client.ts'
import { joinApi, solveChallenge } from '../../api/admission.ts'
import type { FamilyMember, Guardian, JoinSchema, JoinSubmission } from '../../api/admission.ts'
import { errorMessage } from '../../components/forms.ts'
import { Logo } from '../../components/Logo.tsx'
import { Alert, Loading } from '../../components/ui.tsx'
import { lang, t } from '../../i18n/index.ts'
import { LanguageSwitch } from '../../i18n/LanguageControls.tsx'
import {
  type Step,
  type Values,
  empty,
  stepOf,
  confirmKey,
  ageOn,
  askAdult,
  type JoinModel,
} from './joinModel.ts'
import { JoinStepData } from './JoinStepData.tsx'
import { JoinStepFee } from './JoinStepFee.tsx'
import { JoinStepConfirm } from './JoinStepConfirm.tsx'

/** /mitglied-werden/:key (online) und /mitglied-werden/stand/:token (Stand-Modus) */
export function JoinFormPage({ kiosk = false }: { kiosk?: boolean }) {
  const params = useParams()
  const [search] = useSearchParams()
  const key = (kiosk ? params.token : params.key) ?? ''
  const unitHint = search.get('einheit') ?? ''
  // Link „Mitarbeiter melden“ einer Firma (Haushalte und Firmen H5)
  const companyToken = kiosk ? '' : (search.get('firma') ?? '')
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
        const given = d.company ? d.invite : null
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
  const discounts = (schema?.discounts ?? []).filter(
    (d) => d.member_type === null || !type || d.member_type === type.id,
  )
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
      if (askAdult(f.birth_date, person, values.birth_date) && !values.adult)
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
      adult: askAdult(f.birth_date, person, values.birth_date) ? values.adult === 'yes' : null,
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
      discount:
        person && discounts.some((d) => String(d.id) === values.discount)
          ? Number(values.discount)
          : null,
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
              <BackToWebsite schema={s} />
            </>
          )}
        </div>
      </main>
    )
  }

  const steps = [t('Angaben'), t('Beitrag und Zahlung'), t('Bestätigen')]
  const err = (k: string) => errors[k]
  const m: JoinModel = {
    s,
    f,
    kiosk,
    values,
    setValues,
    set,
    toggle,
    setRelative,
    setGuardian,
    err,
    type,
    discounts,
    person,
    minor,
    familyOn,
    confirmations,
    padKey,
    setSignature,
  }

  return (
    <main className="login-page">
      <form className="card public-photo stack-sm join-form" onSubmit={next} noValidate>
        {/* Wappen, Name und Rückweg zur Webseite des Vereins (UX-Audit WS-09/X-08) */}
        {!kiosk && <BackToWebsite schema={s} />}
        <div className="login-logo">
          <Logo name={s.organization} logoUrl={s.logo_url ?? null} />
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

        {step === 0 && <JoinStepData m={m} />}

        {step === 1 && <JoinStepFee m={m} />}

        {step === 2 && <JoinStepConfirm m={m} />}

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

/** Link zurück zur öffentlichen Webseite des Vereins, wenn es eine gibt (UX-Audit WS-09/X-08) */
function BackToWebsite({ schema }: { schema: JoinSchema }) {
  if (!schema.website_url) return null
  return (
    <p className="small join-back">
      <a href={schema.website_url}>
        <span aria-hidden="true">← </span>
        {t('Zurück zur Webseite von {x}', { x: schema.organization })}
      </a>
    </p>
  )
}
