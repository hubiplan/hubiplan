// Eine Umfrage aus Mitgliedersicht: beantworten, ändern, zurückziehen, Ergebnis, Zusage übernehmen.
// Gemeinsam für Mitgliederbereich und persönlichen Mail-Link.
import { useState } from 'react'
import type { AnswerRow, MemberSurvey } from '../../api/surveys.ts'
import { berlin, formatDay } from '../../components/calendar/time.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { SurveyAnswerForm, SurveyResults, endText } from './SurveyParts.tsx'

export function MemberSurveyCard({
  survey,
  busy,
  onAnswer,
  onWithdraw,
  onFollow,
  headingLevel = 2,
  plain = false,
}: {
  survey: MemberSurvey
  busy: boolean
  onAnswer: (answers: AnswerRow[]) => Promise<boolean>
  onWithdraw?: () => void
  onFollow?: () => void
  headingLevel?: 1 | 2 | 3
  /** ohne eigene Karte (öffentliche Seite) */
  plain?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const s = survey
  const Heading = (['h1', 'h2', 'h3'] as const)[headingLevel - 1]
  const showForm = s.can_answer && (!s.answered || editing)
  const follow = s.follow_event
  return (
    <article className={plain ? 'stack-sm survey-member' : 'card stack-sm survey-member'}>
      <Heading>{s.title}</Heading>
      <p className="muted small">
        {[
          s.unit,
          s.event ? t('zum Termin {title}', { title: s.event.title }) : '',
          s.status === 'open' && s.closes_at
            ? t('läuft bis {when}', { when: endText(s.closes_at) })
            : '',
          s.status === 'closed' ? t('beendet') : '',
          s.anonymous ? t('anonym') : '',
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {s.description && <p className="survey-text">{s.description}</p>}
      {follow && (
        <Alert kind="info">
          {t('Termin steht fest: {title} am {day}.', {
            title: follow.title,
            day: formatDay(berlin(follow.starts_at).date),
          })}{' '}
          {follow.response === 'yes' && t('Du hast zugesagt.')}
          {follow.said_yes && follow.rsvp_enabled && follow.response !== 'yes' && onFollow && (
            <span className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={onFollow}
              >
                {t('Zusage übernehmen')}
              </button>
            </span>
          )}
        </Alert>
      )}
      {s.answered && !editing && (
        <p>
          <strong>{t('Du hast geantwortet.')}</strong>{' '}
          {s.anonymous && <span className="muted small">{t('Anonym, nicht mehr änderbar.')}</span>}
        </p>
      )}
      {showForm ? (
        <SurveyAnswerForm
          questions={s.questions}
          mine={s.mine}
          anonymous={s.anonymous}
          busy={busy}
          submitLabel={s.answered ? t('Änderung speichern') : t('Absenden')}
          onSubmit={async (answers) => {
            if (await onAnswer(answers)) setEditing(false)
          }}
          onCancel={editing ? () => setEditing(false) : undefined}
        />
      ) : (
        s.can_change && (
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              {t('Antwort ändern')}
            </button>
            {onWithdraw && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={onWithdraw}
              >
                {t('Antwort zurückziehen')}
              </button>
            )}
          </div>
        )
      )}
      {!s.can_answer && !s.answered && s.status === 'open' && (
        <p className="muted">{t('Du kannst hier nicht mehr antworten.')}</p>
      )}
      {s.results ? (
        <section className="stack-sm" aria-label={t('Ergebnis')}>
          <h3>{t('Ergebnis')}</h3>
          <SurveyResults result={s.results} />
        </section>
      ) : (
        s.answered &&
        s.results_mode !== 'managers' && (
          <p className="muted small">
            {s.results_mode === 'after_close'
              ? t('Das Ergebnis erscheint nach dem Ende der Umfrage.')
              : ''}
          </p>
        )
      )}
    </article>
  )
}
