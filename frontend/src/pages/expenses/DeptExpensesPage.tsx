// Untereinheit › Auslagen: die Leitung bestätigt Auslagen ihrer Untereinheit sachlich, bevor
// die Kasse freigibt (docs/auslagen.md, Stufe A4).
import { useState } from 'react'
import { deptExpenseApi } from '../../api/expenses.ts'
import { PERM } from '../../api/orgs.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { ClaimEvents, ClaimFacts, ClaimFiles, StatusBadge } from './ExpenseParts.tsx'
import { euro } from './format.ts'
import { NoAccessPage } from '../NoticePages.tsx'

export function DeptExpensesPage() {
  const { activeDept } = useOrg()
  if (!activeDept?.expenses_enabled || !activeDept.permissions.includes(PERM.expensesView))
    return <NoAccessPage reason="right" />
  return (
    <section>
      <PageHeader />
      <DeptExpenses key={activeDept.id} deptId={activeDept.id} />
    </section>
  )
}

function DeptExpenses({ deptId }: { deptId: number }) {
  const list = useLoad(() => deptExpenseApi.list(deptId), [deptId])
  const detail = useDetailParam('auslage')
  if (list.error) return <LoadError message={list.error} onRetry={list.reload} />
  if (!list.data) return <Loading />
  if (detail.value)
    return (
      <DeptClaim
        deptId={deptId}
        id={Number(detail.value)}
        canConfirm={list.data.can_confirm}
        onBack={() => {
          detail.close()
          void list.reload()
        }}
      />
    )
  return (
    <div className="stack">
      <p>
        {t(
          'Auslagen für diese Untereinheit. Die Leitung bestätigt sachlich, dass die Ausgabe für sie war; danach prüft und zahlt die Kasse.',
        )}
      </p>
      {list.data.waiting > 0 && (
        <Alert kind="info">
          {t('{n} Auslagen warten auf eure Bestätigung.', { n: list.data.waiting })}
        </Alert>
      )}
      {!list.data.claims.length ? (
        <EmptyState title={t('Keine Auslagen')}>
          {t('Für diese Untereinheit ist noch keine Auslage eingereicht.')}
        </EmptyState>
      ) : (
        <ul className="expense-list">
          {list.data.claims.map((c) => (
            <li key={c.id} className="card">
              <div className="expense-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => detail.open(String(c.id))}
                >
                  {c.number} · {c.name} · {c.purpose}
                </button>
                <span>
                  {euro(c.total)} <StatusBadge claim={c} />
                  {c.needs_confirm && (
                    <span className="badge badge-warn">{t('bitte bestätigen')}</span>
                  )}
                </span>
              </div>
              {c.submitted_at && (
                <p className="muted small">
                  {t('eingereicht am {day}', { day: formatDate(c.submitted_at) })}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DeptClaim({
  deptId,
  id,
  canConfirm,
  onBack,
}: {
  deptId: number
  id: number
  canConfirm: boolean
  onBack: () => void
}) {
  const load = useLoad(() => deptExpenseApi.get(deptId, id), [deptId, id])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  const claim = load.data
  if (!claim) return <Loading />
  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setFailure('')
    try {
      await action()
      await load.reload()
      setNotice(done)
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="stack">
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={onBack}>
          {t('Zurück zur Liste')}
        </button>
      </div>
      <section className="card stack">
        <div className="expense-row">
          <h2>
            {claim.number} · {claim.name}
          </h2>
          <StatusBadge claim={claim} />
        </div>
        <p>{claim.purpose}</p>
        {notice && <Alert kind="success">{notice}</Alert>}
        {failure && <Alert kind="error">{failure}</Alert>}
        <ClaimFacts claim={claim} />
        <h3>{t('Belege')}</h3>
        <ClaimFiles claim={claim} url={(f) => deptExpenseApi.fileUrl(deptId, id, f)} />
        {canConfirm && claim.can_confirm && (
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                void run(
                  () => deptExpenseApi.action(deptId, id, 'confirm', { version: claim.version }),
                  t('Sachlich bestätigt. Jetzt prüft die Kasse.'),
                )
              }
            >
              {t('Sachlich bestätigen')}
            </button>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={async () => {
                const text = await promptDialog({
                  title: t('Rückfrage an {name}', { name: claim.name }),
                  label: t('Was fehlt oder ist unklar?'),
                  confirmLabel: t('Rückfrage senden'),
                  danger: false,
                })
                if (text)
                  await run(
                    () =>
                      deptExpenseApi.action(deptId, id, 'ask', { text, version: claim.version }),
                    t('Rückfrage gesendet.'),
                  )
              }}
            >
              {t('Rückfrage stellen')}
            </button>
          </div>
        )}
        <ClaimEvents claim={claim} />
      </section>
    </div>
  )
}
