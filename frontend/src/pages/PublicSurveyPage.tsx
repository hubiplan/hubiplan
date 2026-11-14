// Umfrage über den persönlichen Link aus der Mail beantworten (ohne Anmeldung).
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { publicSurveyApi } from '../api/surveys.ts'
import type { AnswerRow, PublicSurvey } from '../api/surveys.ts'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePublicImprint } from '../components/publicImprint.ts'
import { Alert, Loading } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'
import { MemberSurveyCard } from './surveys/MemberSurveyCard.tsx'

export function PublicSurveyPage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<PublicSurvey | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  usePublicImprint(info?.imprint_key, info?.club)

  useEffect(() => {
    let alive = true
    publicSurveyApi
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

  async function answer(answers: AnswerRow[]) {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      setInfo(await publicSurveyApi.answer(token, answers))
      setNotice(t('Danke, deine Antwort ist gespeichert.'))
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <div className="card public-photo stack-sm survey-public">
        <div className="login-logo">
          <Logo name={info?.club} logoUrl={null} />
        </div>
        {!info && <h1>{t('Umfrage')}</h1>}
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
            <p className="muted">
              {info.club} · {t('Hallo {first_name}', { first_name: info.first_name })}
            </p>
            {notice && <Alert kind="success">{notice}</Alert>}
            {error && <Alert kind="error">{error}</Alert>}
            <MemberSurveyCard
              survey={info.survey}
              busy={busy}
              onAnswer={answer}
              headingLevel={1}
              plain
            />
          </>
        )}
      </div>
    </main>
  )
}
