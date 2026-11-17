// Nachweis für einen ermäßigten Beitrag über den Link aus der Erinnerung hochladen, ohne
// Anmeldung (docs/beitragsnachweise.md).
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { publicFeeProofApi } from '../api/feeProofs.ts'
import type { PublicFeeProof } from '../api/feeProofs.ts'
import { errorMessage, formatDate } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePublicImprint } from '../components/publicImprint.ts'
import { Alert, Loading } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'
import { ProofStatusBadge, StateBadge, UploadForm, stateSentence } from './feeproofs/parts.tsx'

export function PublicFeeProofPage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<PublicFeeProof | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  usePublicImprint(info?.imprint_key, info?.club)

  useEffect(() => {
    let alive = true
    publicFeeProofApi
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

  async function submit(file: File, kind: string, note: string) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setInfo(await publicFeeProofApi.submit(token, { kind, note }, file))
      setNotice(t('Danke! Dein Nachweis ist eingegangen. Der Vorstand prüft ihn.'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const st = info?.state
  return (
    <main className="login-page">
      <div className="card public-photo stack">
        <div className="login-logo">
          <Logo name={info?.club} logoUrl={null} />
        </div>
        <h1>{t('Nachweis einreichen')}</h1>
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
        {info && st && (
          <>
            <p>
              {t(
                'Hallo {name}, hier reichst du den Nachweis für „{discount}“ {year} bei {club} ein.',
                {
                  name: info.first_name,
                  discount: st.discount_name,
                  year: st.year_label,
                  club: info.club,
                },
              )}
            </p>
            <p>
              <StateBadge state={st.state} /> {stateSentence(st)}
            </p>
            {notice && <Alert kind="success">{notice}</Alert>}
            {st.state !== 'accepted' && (
              <UploadForm
                kinds={st.kinds}
                busy={busy}
                error={error}
                onSubmit={(f, k, n) => void submit(f, k, n)}
              />
            )}
            {info.proofs.length > 0 && (
              <section className="stack">
                <h2>{t('Eingereicht')}</h2>
                <ul className="expense-items">
                  {info.proofs.map((p) => (
                    <li key={p.id}>
                      {formatDate(p.received_on)}
                      {p.file_name ? ` · ${p.file_name}` : ''} <ProofStatusBadge proof={p} />
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
