// Umfragen im Mitgliederbereich: offene zuerst, dann beendete mit Ergebnis.
import { useState } from 'react'
import { portalSurveyApi } from '../../api/surveys.ts'
import type { AnswerRow, MemberSurvey } from '../../api/surveys.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { MemberSurveyCard } from '../surveys/MemberSurveyCard.tsx'

export function PortalSurveys({ accessId }: { accessId: number }) {
  const { data, error, reload } = useLoad(() => portalSurveyApi.list(accessId), [accessId])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const run = async (action: () => Promise<MemberSurvey>, done = '') => {
    setBusy(true)
    setFailure(null)
    setNotice('')
    try {
      await action()
      await reload()
      setNotice(done)
      return true
    } catch (err) {
      setFailure(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  const withdraw = async (s: MemberSurvey) => {
    const yes = await confirmDialog({
      final: false,
      title: t('Antwort zurückziehen?'),
      message: s.title,
      confirmLabel: t('Antwort zurückziehen'),
    })
    if (yes) await run(() => portalSurveyApi.withdraw(accessId, s.id), t('Antwort zurückgezogen.'))
  }
  const open = data.surveys.filter((s) => s.status === 'open')
  const closed = data.surveys.filter((s) => s.status !== 'open')
  return (
    <div className="stack">
      {notice && <Alert kind="success">{notice}</Alert>}
      {failure && <Alert kind="error">{failure}</Alert>}
      {!data.surveys.length && (
        <EmptyState title={t('Keine Umfragen')}>
          {t('Gerade läuft keine Umfrage für dich.')}
        </EmptyState>
      )}
      {open.map((s) => (
        <MemberSurveyCard
          key={s.id}
          survey={s}
          busy={busy}
          onAnswer={(answers: AnswerRow[]) =>
            run(
              () => portalSurveyApi.answer(accessId, s.id, answers),
              t('Danke, deine Antwort ist gespeichert.'),
            )
          }
          onWithdraw={() => withdraw(s)}
          onFollow={() =>
            run(() => portalSurveyApi.follow(accessId, s.id), t('Zusage gespeichert.'))
          }
        />
      ))}
      {closed.length > 0 && <h2>{t('Beendete Umfragen')}</h2>}
      {closed.map((s) => (
        <MemberSurveyCard
          key={s.id}
          survey={s}
          busy={busy}
          headingLevel={3}
          onAnswer={async () => false}
          onFollow={() =>
            run(() => portalSurveyApi.follow(accessId, s.id), t('Zusage gespeichert.'))
          }
        />
      ))}
    </div>
  )
}
