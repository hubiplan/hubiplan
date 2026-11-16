// Auslage über den persönlichen Link einreichen (ohne Zugang, docs/auslagen.md, Stufe A6).
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { publicExpenseApi } from '../api/expenses.ts'
import type { ClaimInput, PublicExpense } from '../api/expenses.ts'
import { formatDate } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePublicImprint } from '../components/publicImprint.ts'
import { Alert, Loading } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'
import { ClaimForm, StatusBadge } from './expenses/ExpenseParts.tsx'
import { euro, formErrors } from './expenses/format.ts'

export function PublicExpensePage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<PublicExpense | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')
  const [formKey, setFormKey] = useState(0)
  usePublicImprint(info?.imprint_key, info?.club)

  useEffect(() => {
    let alive = true
    publicExpenseApi
      .get(token)
      .then((d) => alive && setInfo(d))
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) setInvalid(true)
        else setUnavailable(true)
      })
    return () => {
      alive = false
    }
  }, [token, attempt])

  async function submit(data: ClaimInput, files: File[]) {
    setBusy(true)
    setErrors({})
    setNotice('')
    try {
      setInfo(await publicExpenseApi.submit(token, data, files))
      setNotice(t('Danke! Deine Auslage ist eingereicht. Die Kasse meldet sich.'))
      setFormKey((k) => k + 1)
    } catch (err) {
      setErrors(formErrors(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <div className="card public-photo stack">
        <div className="login-logo">
          <Logo name={info?.club} logoUrl={null} />
        </div>
        <h1>{t('Auslage einreichen')}</h1>
        {invalid && <Alert kind="error">{t('Dieser Link ist ungültig oder abgelaufen.')}</Alert>}
        {unavailable && (
          <>
            <Alert kind="error">
              {t('Die Seite kann gerade nicht geladen werden. Bitte später erneut versuchen.')}
            </Alert>
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                onClick={() => {
                  setUnavailable(false)
                  setAttempt((n) => n + 1)
                }}
              >
                {t('Erneut versuchen')}
              </button>
            </div>
          </>
        )}
        {!info && !invalid && !unavailable && <Loading />}
        {info && (
          <>
            <p>
              {t(
                'Hallo {name}, hier meldest du Ausgaben, die du für {club} selbst bezahlt hast. Der Link gilt bis {day}.',
                { name: info.name, club: info.club, day: formatDate(info.valid_until) },
              )}
            </p>
            {notice && <Alert kind="success">{notice}</Alert>}
            <ClaimForm
              key={formKey}
              choices={{ mileage_enabled: info.mileage_enabled, km_rate: info.km_rate }}
              errors={errors}
              busy={busy}
              allowDraft={false}
              onSubmit={(data, files) => void submit(data, files)}
            />
            {info.claims.length > 0 && (
              <section className="stack">
                <h2>{t('Deine Auslagen')}</h2>
                <ul className="expense-list">
                  {info.claims.map((c) => (
                    <li key={c.id} className="expense-row">
                      <span>
                        {c.number} · {c.purpose}
                      </span>
                      <span>
                        {euro(c.amount_due)} <StatusBadge claim={c} />
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </main>
  )
}
