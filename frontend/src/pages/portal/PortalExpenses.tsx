// Mein Bereich › Auslagen: selbst bezahlte Ausgaben mit Foto des Belegs melden, Rückfragen
// beantworten, Stand verfolgen (docs/auslagen.md).
import { useState } from 'react'
import { portalExpenseApi } from '../../api/expenses.ts'
import type { ClaimInput, MemberOptions } from '../../api/expenses.ts'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import {
  ClaimEvents,
  ClaimFacts,
  ClaimFiles,
  ClaimForm,
  StatusBadge,
} from '../expenses/ExpenseParts.tsx'
import { euro, formErrors } from '../expenses/format.ts'

export function PortalExpenses({ accessId }: { accessId: number }) {
  const { data, error, reload } = useLoad(() => portalExpenseApi.list(accessId), [accessId])
  const detail = useDetailParam('auslage')
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const { options } = data
  if (detail.value)
    return (
      <ClaimDetail
        accessId={accessId}
        id={Number(detail.value)}
        options={options}
        onBack={() => {
          detail.close()
          void reload()
        }}
      />
    )
  const create = async (input: ClaimInput, files: File[], submit: boolean) => {
    setBusy(true)
    setErrors({})
    try {
      const claim = await portalExpenseApi.create(accessId, input, files, submit)
      setCreating(false)
      setNotice(
        submit
          ? t('Auslage {number} ist eingereicht. Du bekommst Bescheid, sobald sie geprüft ist.', {
              number: claim.number,
            })
          : t('Entwurf gespeichert.'),
      )
      await reload()
    } catch (err) {
      setErrors(formErrors(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="stack">
      {notice && <Alert kind="success">{notice}</Alert>}
      {!options.may_submit && (
        <Alert kind="info">
          {t('Auslagen melden hier nur Personen mit Amt oder Rolle im Verein.')}
        </Alert>
      )}
      {creating ? (
        <section className="card stack">
          <h2>{t('Neue Auslage')}</h2>
          <ClaimForm
            choices={options}
            errors={errors}
            busy={busy}
            onSubmit={create}
            onCancel={() => {
              setCreating(false)
              setErrors({})
            }}
          />
        </section>
      ) : (
        options.may_submit && (
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              onClick={() => {
                setNotice('')
                setCreating(true)
              }}
            >
              {t('Auslage melden')}
            </button>
          </div>
        )
      )}
      {!data.claims.length && !creating && (
        <EmptyState title={t('Noch keine Auslagen')}>
          {t(
            'Hast du etwas für den Verein selbst bezahlt? Melde es hier mit einem Foto des Belegs, die Kasse erstattet dir den Betrag.',
          )}
        </EmptyState>
      )}
      {data.claims.length > 0 && (
        <ul className="expense-list" aria-label={t('Meine Auslagen')}>
          {data.claims.map((c) => (
            <li key={c.id} className="card">
              <div className="expense-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => detail.open(String(c.id))}
                >
                  {c.number || t('Entwurf')} · {c.purpose || t('ohne Zweck')}
                </button>
                <span>
                  {euro(c.amount_due)} <StatusBadge claim={c} />
                </span>
              </div>
              <p className="muted small">
                {c.submitted_at
                  ? t('eingereicht am {day}', { day: formatDate(c.submitted_at) })
                  : t('angelegt am {day}', { day: formatDate(c.created_at) })}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ClaimDetail({
  accessId,
  id,
  options,
  onBack,
}: {
  accessId: number
  id: number
  options: MemberOptions
  onBack: () => void
}) {
  const load = useLoad(() => portalExpenseApi.get(accessId, id), [accessId, id])
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  const [answer, setAnswer] = useState('')
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  const claim = load.data
  if (!claim) return <Loading />
  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setFailure('')
    setNotice('')
    try {
      await action()
      await load.reload()
      setNotice(done)
      return true
    } catch (err) {
      setFailure(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  const save = async (input: ClaimInput, files: File[], submit: boolean) => {
    setBusy(true)
    setErrors({})
    try {
      await portalExpenseApi.update(accessId, id, { ...input, version: claim.version })
      for (const file of files) await portalExpenseApi.addFile(accessId, id, file)
      if (submit && claim.status === 'draft') await portalExpenseApi.action(accessId, id, 'submit')
      setEditing(false)
      setNotice(submit && claim.status === 'draft' ? t('Auslage eingereicht.') : t('Gespeichert.'))
      await load.reload()
    } catch (err) {
      setErrors(formErrors(err))
      await load.reload()
    } finally {
      setBusy(false)
    }
  }
  const question = [...(claim.events ?? [])].reverse().find((e) => e.kind === 'question')
  const url = (fileId: number) => portalExpenseApi.fileUrl(accessId, id, fileId)
  return (
    <div className="stack">
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={onBack}>
          {t('Zurück zu den Auslagen')}
        </button>
      </div>
      <section className="card stack">
        <div className="expense-row">
          <h2>{claim.number || t('Entwurf')}</h2>
          <StatusBadge claim={claim} />
        </div>
        <p>{claim.purpose}</p>
        {notice && <Alert kind="success">{notice}</Alert>}
        {failure && <Alert kind="error">{failure}</Alert>}
        {claim.status === 'question' && question && (
          <Alert kind="info">{t('Rückfrage der Kasse: {text}', { text: question.text })}</Alert>
        )}
        {editing ? (
          <ClaimForm
            claim={claim}
            choices={options}
            errors={errors}
            busy={busy}
            allowDraft={claim.status === 'draft'}
            submitLabel={claim.status === 'draft' ? t('Einreichen') : t('Speichern')}
            onSubmit={(input, files, submit) =>
              save(input, files, submit || claim.status !== 'draft')
            }
            onCancel={() => setEditing(false)}
          />
        ) : (
          <>
            <ClaimFacts claim={claim} />
            <h3>{t('Belege')}</h3>
            <ClaimFiles
              claim={claim}
              url={url}
              onRemove={
                claim.status === 'draft'
                  ? (fileId) =>
                      void run(
                        () => portalExpenseApi.removeFile(accessId, id, fileId),
                        t('Beleg entfernt.'),
                      )
                  : undefined
              }
            />
            {claim.can_edit && claim.kind === 'expense' && (
              <label className="button button-ghost file-button">
                {t('Beleg ergänzen')}
                <input
                  type="file"
                  className="file-input"
                  accept="image/*,application/pdf,.pdf,.xml,application/xml"
                  capture="environment"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (file)
                      void run(
                        () => portalExpenseApi.addFile(accessId, id, file),
                        t('Beleg hinzugefügt.'),
                      )
                  }}
                />
              </label>
            )}
            {claim.status === 'draft' &&
              claim.problems &&
              Object.keys(claim.problems).length > 0 && (
                <Alert kind="info">
                  {t('Zum Einreichen fehlt noch: {list}', {
                    list: Object.values(claim.problems).join(' '),
                  })}
                </Alert>
              )}
            {claim.status === 'question' && (
              <form
                className="stack"
                onSubmit={async (e) => {
                  e.preventDefault()
                  if (
                    await run(
                      () => portalExpenseApi.action(accessId, id, 'answer', { text: answer }),
                      t('Antwort gesendet. Die Kasse prüft erneut.'),
                    )
                  )
                    setAnswer('')
                }}
              >
                <label className="field">
                  <span>{t('Deine Antwort')}</span>
                  <textarea
                    value={answer}
                    rows={3}
                    maxLength={2000}
                    onChange={(e) => setAnswer(e.target.value)}
                  />
                </label>
                <div className="button-row">
                  <button type="submit" className="button button-primary" disabled={busy}>
                    {t('Antwort senden')}
                  </button>
                </div>
              </form>
            )}
            <div className="button-row">
              {claim.can_edit && (
                <button type="button" className="button" onClick={() => setEditing(true)}>
                  {t('Ändern')}
                </button>
              )}
              {claim.status === 'draft' && (
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy}
                  onClick={() =>
                    void run(
                      () => portalExpenseApi.action(accessId, id, 'submit'),
                      t('Auslage eingereicht.'),
                    )
                  }
                >
                  {t('Einreichen')}
                </button>
              )}
              {claim.can_waive && (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={async () => {
                    const yes = await confirmDialog({
                      title: t('Auf die Erstattung verzichten?'),
                      message: t(
                        'Du verzichtest auf {amount}. Der Verein stellt dir dafür eine Zuwendungsbestätigung (Aufwandsspende) aus. Das lässt sich nicht rückgängig machen.',
                        { amount: euro(claim.amount_due) },
                      ),
                      confirmLabel: t('Verzichten und spenden'),
                      danger: false,
                    })
                    if (yes)
                      await run(
                        () => portalExpenseApi.action(accessId, id, 'waive'),
                        t('Danke! Die Zuwendungsbestätigung kommt von der Kasse.'),
                      )
                  }}
                >
                  {t('Als Spende verzichten')}
                </button>
              )}
              {claim.can_withdraw && (
                <button
                  type="button"
                  className="button button-danger"
                  disabled={busy}
                  onClick={async () => {
                    const yes = await confirmDialog({
                      title:
                        claim.status === 'draft' && !claim.number
                          ? t('Entwurf löschen?')
                          : t('Auslage zurückziehen?'),
                      message: claim.purpose,
                      confirmLabel:
                        claim.status === 'draft' && !claim.number
                          ? t('Löschen')
                          : t('Zurückziehen'),
                    })
                    if (!yes) return
                    if (claim.status === 'draft' && !claim.number) {
                      setBusy(true)
                      try {
                        await portalExpenseApi.remove(accessId, id)
                        onBack()
                      } catch (err) {
                        setFailure(errorMessage(err))
                        setBusy(false)
                      }
                    } else
                      await run(
                        () => portalExpenseApi.action(accessId, id, 'withdraw'),
                        t('Auslage zurückgezogen.'),
                      )
                  }}
                >
                  {claim.status === 'draft' && !claim.number ? t('Löschen') : t('Zurückziehen')}
                </button>
              )}
            </div>
          </>
        )}
        <ClaimEvents claim={claim} />
      </section>
    </div>
  )
}
