// Finanzen › Auslagen: prüfen, freigeben, auszahlen, Sammelüberweisung, Links für Personen
// ohne Zugang und Einstellungen (docs/auslagen.md).
import { useRowSort } from '../../components/RowSort.tsx'
import { useState } from 'react'
import { expenseApi } from '../../api/expenses.ts'
import type { ClaimInput, ExpenseClaim, ExpenseTab } from '../../api/expenses.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageActions, Segmented } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, Field, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ClaimForm, StatusBadge } from './ExpenseParts.tsx'
import { euro, formErrors } from './format.ts'
import { Term } from '../../learning/Aids.tsx'
import { ClaimPanel } from './ClaimPanel.tsx'

export function ExpensesPage() {
  const org = useActiveOrg()
  const view = useDetailParam('ansicht')
  const detail = useDetailParam('auslage')
  const tab = (view.value as ExpenseTab | null) ?? 'review'
  const list = useLoad(() => expenseApi.list(org.id, tab), [org.id, tab])
  const [creating, setCreating] = useState(false)
  const [picked, setPicked] = useState<number[]>([])
  const [notice, setNotice] = useState('')
  const [failure, setFailure] = useState('')
  const sorting = useRowSort(list.data?.claims ?? [], {
    number: (c) => c.number,
    name: (c) => c.name,
    purpose: (c) => c.purpose,
    amount: (c) => Number(c.amount_due),
    status: (c) => c.status,
  })
  if (detail.value)
    return (
      <ClaimPanel
        id={Number(detail.value)}
        onBack={() => {
          detail.close()
          void list.reload()
        }}
      />
    )
  if (creating)
    return (
      <TreasuryCreate
        onDone={(claim) => {
          setCreating(false)
          if (claim) detail.open(String(claim.id))
          else void list.reload()
        }}
      />
    )
  const data = list.data
  const tabs: { value: ExpenseTab; label: string }[] = [
    {
      value: 'review',
      label: data?.counts.review ? t('Zu prüfen ({n})', { n: data.counts.review }) : t('Zu prüfen'),
    },
    {
      value: 'approved',
      label: data?.counts.approved
        ? t('Freigegeben ({n})', { n: data.counts.approved })
        : t('Freigegeben'),
    },
    { value: 'done', label: t('Erledigt') },
    {
      value: 'unreviewed',
      label: data?.counts.unreviewed
        ? t('Nachträglich sichten ({n})', { n: data.counts.unreviewed })
        : t('Nachträglich sichten'),
    },
    { value: 'drafts', label: t('Entwürfe der Kasse') },
  ]
  const reviewPicked = async () => {
    setFailure('')
    try {
      const result = await expenseApi.review(org.id, picked)
      setNotice(t('{n} Auslagen gesichtet.', { n: result.reviewed }))
      setPicked([])
      await list.reload()
    } catch (err) {
      setFailure(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      {data?.can_edit && (
        <PageActions
          primary={{ label: t('Für jemanden erfassen'), onClick: () => setCreating(true) }}
        />
      )}
      <Segmented
        label={t('Ansicht')}
        options={tabs}
        value={tab}
        onChange={(v) => (v === 'review' ? view.close() : view.replace(v))}
      />
      {data && data.summary.approved_count > 0 && (
        <p className="muted">
          {t('Freigegeben und noch nicht ausgezahlt: {n} Auslagen über {sum}', {
            n: data.summary.approved_count,
            sum: euro(data.summary.approved_sum),
          })}
        </p>
      )}
      {notice && <Alert kind="success">{notice}</Alert>}
      {failure && <Alert kind="error">{failure}</Alert>}
      {list.error && <LoadError message={list.error} onRetry={list.reload} />}
      {!data && !list.error && <Loading />}
      {data && !data.claims.length && (
        <EmptyState title={t('Keine Auslagen')}>
          {tab === 'review'
            ? t('Gerade wartet keine Auslage auf die Prüfung.')
            : t('In dieser Ansicht steht nichts.')}
        </EmptyState>
      )}
      {data && data.claims.length > 0 && (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                {tab === 'unreviewed' && <th>{t('Auswahl')}</th>}
                {sorting.head('number', t('Nummer'))}
                {sorting.head('name', t('Von'))}
                {sorting.head('purpose', t('Zweck'))}
                {sorting.head('amount', t('Betrag'))}
                {sorting.head('status', t('Stand'))}
              </tr>
            </thead>
            <tbody>
              {sorting.rows.map((c) => (
                <tr key={c.id}>
                  {tab === 'unreviewed' && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t('{number} auswählen', { number: c.number })}
                        checked={picked.includes(c.id)}
                        disabled={c.own}
                        onChange={(e) =>
                          setPicked(
                            e.target.checked ? [...picked, c.id] : picked.filter((i) => i !== c.id),
                          )
                        }
                      />
                    </td>
                  )}
                  <td>
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => detail.open(String(c.id))}
                    >
                      {c.number || t('Entwurf')}
                    </button>
                  </td>
                  <td>{c.name}</td>
                  <td>{c.purpose}</td>
                  <td>{euro(c.amount_due)}</td>
                  <td>
                    <StatusBadge claim={c} />
                    {c.self_approved && !c.reviewed && (
                      <span className="badge badge-warn">{t('selbst freigegeben')}</span>
                    )}
                    {c.file_count === 0 && c.kind === 'expense' && (
                      <span className="badge">{t('ohne Beleg')}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === 'unreviewed' && picked.length > 0 && (
        <div className="button-row">
          <button type="button" className="button button-primary" onClick={reviewPicked}>
            {t('Ausgewählte als gesichtet markieren')}
          </button>
        </div>
      )}
    </div>
  )
}

function TreasuryCreate({ onDone }: { onDone: (claim: ExpenseClaim | null) => void }) {
  const org = useActiveOrg()
  const options = useLoad(() => expenseApi.options(org.id), [org.id])
  const settings = useLoad(() => expenseApi.settings(org.id), [org.id])
  const [member, setMember] = useState<PickedMember | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  if (options.error || settings.error)
    return <LoadError message={options.error || settings.error || ''} onRetry={options.reload} />
  if (!options.data || !settings.data) return <Loading />
  const save = async (input: ClaimInput, files: File[], submit: boolean) => {
    setBusy(true)
    setErrors({})
    try {
      let claim = await expenseApi.create(org.id, {
        ...input,
        ...(member ? { membership: member.id } : { name }),
      })
      for (const file of files) claim = await expenseApi.addFile(org.id, claim.id, file)
      if (submit) claim = await expenseApi.action(org.id, claim.id, 'submit')
      onDone(claim)
    } catch (err) {
      setErrors(formErrors(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      <h2>
        <Term k="expense_claim">{t('Auslage für jemanden erfassen')}</Term>
      </h2>
      <p className="muted">
        {t(
          'Zum Beispiel für einen Kassenzettel, der in Papierform abgegeben wurde. Ohne Beleg braucht es eine Begründung (Eigenbeleg).',
        )}
      </p>
      <MemberPicker orgId={org.id} value={member} onChange={setMember} />
      {!member && (
        <Field
          label={t('Oder Name einer Person ohne Mitgliedschaft')}
          value={name}
          maxLength={200}
          error={errors.name || errors.membership}
          onChange={(e) => setName(e.target.value)}
        />
      )}
      <ClaimForm
        choices={{
          mileage_enabled: settings.data.mileage_enabled,
          km_rate: settings.data.km_rate,
          categories: options.data.categories,
          departments: settings.data.departments,
        }}
        treasury
        errors={errors}
        busy={busy}
        onSubmit={save}
        onCancel={() => onDone(null)}
      />
    </section>
  )
}
