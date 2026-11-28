import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { surveyApi } from '../../api/surveys.ts'
import type { SurveyMember } from '../../api/surveys.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { SurveyAnswerForm, SurveyResults, dateLabel, endText } from './SurveyParts.tsx'
import './surveys.css'
import { SurveyEditor } from './SurveyEditor.tsx'
import {
  kindLabel,
  local,
  namesLabel,
  resultsLabel,
  statusLabel,
  toApiTime,
} from './surveysHelpers.ts'

export function SurveyDetail({
  base,
  orgId,
  id,
  onClose,
  onOpen,
}: {
  base: string
  orgId: number
  id: number
  onClose: () => void
  onOpen: (id: number) => Promise<void>
}) {
  const navigate = useNavigate()
  const loaded = useLoad(() => surveyApi.get(base, id), [base, id])
  const [editing, setEditing] = useState(false)
  const [entering, setEntering] = useState(false)
  const [member, setMember] = useState<SurveyMember | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [end, setEnd] = useState('')
  const s = loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!s) return <Loading />
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
      await loaded.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (editing) {
    return (
      <SurveyEditor
        base={base}
        survey={s}
        onDone={async (saved) => {
          setEditing(false)
          if (saved) await loaded.reload()
        }}
      />
    )
  }
  const dates = (s.questions ?? []).find((q) => q.kind === 'dates')
  const best = s.result?.questions.find((q) => q.kind === 'dates')?.best ?? []
  return (
    <div className="surveys stack">
      <PageHeader
        title={s.title}
        status={<span className="badge">{statusLabel(s.status)}</span>}
        onBack={onClose}
      />
      {s.description && <p>{s.description}</p>}
      <p className="muted">
        {s.event_title && `${s.event_title} · `}
        {s.closes_at && t('Ende: {x}', { x: endText(s.closes_at) })}
        {' · '}
        {namesLabel(s.names)}
        {' · '}
        {t('Ergebnis für Befragte: {x}', { x: resultsLabel(s.results) })}
      </p>
      {error && <p role="alert">{error}</p>}
      {s.can_edit && (
        <div className="button-row">
          {s.status === 'draft' && (
            <>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditing(true)}
              >
                {t('Bearbeiten')}
              </button>
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={async () => {
                  const okay = await confirmDialog({
                    title: t('Umfrage starten?'),
                    message: t(
                      'Alle Befragten bekommen Bescheid, per App oder per E-Mail. Fragen und Zielgruppe lassen sich danach nicht mehr ändern.',
                    ),
                    confirmLabel: t('Starten'),
                    danger: false,
                  })
                  if (okay) await run(() => surveyApi.start(base, s.id))
                }}
              >
                {t('Starten')}
              </button>
            </>
          )}
          {s.status === 'open' && (
            <>
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  const okay = await confirmDialog({
                    title: t('Umfrage beenden?'),
                    message: t('Danach kann niemand mehr antworten.'),
                    confirmLabel: t('Beenden'),
                    danger: false,
                  })
                  if (okay) await run(() => surveyApi.close(base, s.id))
                }}
              >
                {t('Jetzt beenden')}
              </button>
              {s.names !== 'anonymous' && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setEntering(true)}
                >
                  {t('Für ein Mitglied eintragen')}
                </button>
              )}
            </>
          )}
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const copy = await surveyApi.copy(base, s.id)
                await onOpen(copy.id)
              })
            }
          >
            {t('Kopieren')}
          </button>
          {s.status !== 'open' && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={async () => {
                const okay = await confirmDialog({
                  final: true,
                  title: t('Umfrage löschen?'),
                  message: t('Die Umfrage und alle Antworten werden gelöscht.'),
                  confirmLabel: t('Löschen'),
                })
                if (okay) {
                  await run(() => surveyApi.remove(base, s.id))
                  onClose()
                }
              }}
            >
              {t('Löschen')}
            </button>
          )}
        </div>
      )}
      {s.status !== 'draft' && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () =>
                saveBlob(await surveyApi.export(base, s.id, 'pdf'), `umfrage-${s.id}.pdf`),
              )
            }
          >
            {t('PDF')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () =>
                saveBlob(await surveyApi.export(base, s.id, 'xlsx'), `umfrage-${s.id}.xlsx`),
              )
            }
          >
            {t('Excel')}
          </button>
        </div>
      )}
      {s.can_edit && s.status === 'open' && (
        <form
          className="button-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (end) run(() => surveyApi.update(base, s, { closes_at: toApiTime(end) }))
          }}
        >
          <label className="field">
            <span>{t('Ende verschieben')}</span>
            <input
              type="datetime-local"
              value={end || local(s.closes_at)}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <button className="button button-ghost" disabled={busy || !end}>
            {t('Übernehmen')}
          </button>
        </form>
      )}
      {entering && s.questions && (
        <div className="card stack">
          <h2>{t('Für ein Mitglied eintragen')}</h2>
          <MemberPicker<SurveyMember>
            orgId={orgId}
            value={member}
            label={t('Mitglied')}
            search={(term) => surveyApi.members(base, term)}
            onChange={setMember}
          />
          {member && (
            <SurveyAnswerForm
              key={member.id}
              questions={s.questions}
              mine={null}
              anonymous={false}
              busy={busy}
              submitLabel={t('Eintragen')}
              onCancel={() => setEntering(false)}
              onSubmit={(answers) =>
                run(async () => {
                  await surveyApi.answerFor(base, s.id, member.id, answers)
                  setEntering(false)
                  setMember(null)
                })
              }
            />
          )}
        </div>
      )}
      {s.status === 'draft' ? (
        <section className="card stack-sm">
          <h2>{t('Fragen')}</h2>
          <ul className="plain-list">
            {(s.questions ?? []).map((q) => (
              <li key={q.id}>
                <strong>{q.text}</strong> <span className="muted small">({kindLabel(q.kind)})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section className="card stack-sm">
          <h2>{t('Ergebnis')}</h2>
          <p className="muted small">
            {s.invited != null
              ? t('{n} von {m} haben geantwortet.', { n: s.participants, m: s.invited })
              : t('{n} haben geantwortet.', { n: s.participants })}{' '}
            {t('Meinungsbild, kein Beschluss.')}
          </p>
          {s.result && <SurveyResults result={s.result} />}
          {dates && s.can_create_event && !s.follow_event && (
            <div className="button-row">
              {dates.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className={best.includes(o.id!) ? 'button button-primary' : 'button button-ghost'}
                  disabled={busy}
                  onClick={async () => {
                    const okay = await confirmDialog({
                      title: t('Termin anlegen?'),
                      message: t(
                        'Aus „{x}“ entsteht ein Termin mit Zu- und Absagen. Wer hier „Ja“ gesagt hat, kann die Zusage mit einem Tipp übernehmen.',
                        { x: dateLabel(o) },
                      ),
                      confirmLabel: t('Termin anlegen'),
                      danger: false,
                    })
                    if (okay) await run(() => surveyApi.eventFrom(base, s.id, o.id!))
                  }}
                >
                  {t('Termin am {x} anlegen', { x: dateLabel(o) })}
                </button>
              ))}
            </div>
          )}
          {s.follow_event && (
            <p>
              <button
                type="button"
                className="link-button"
                onClick={() => navigate(`/termine?termin=${s.follow_event}`)}
              >
                {t('Zum angelegten Termin')}
              </button>
            </p>
          )}
          {s.pending && s.pending.length > 0 && (
            <details>
              <summary>{t('Noch ohne Antwort ({n})', { n: s.pending.length })}</summary>
              <p className="small">{s.pending.join(', ')}</p>
            </details>
          )}
        </section>
      )}
    </div>
  )
}
