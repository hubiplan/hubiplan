// Finanzen › Auslagen: prüfen, freigeben, auszahlen, Sammelüberweisung, Links für Personen
// ohne Zugang und Einstellungen (docs/auslagen.md).
import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { saveBlob } from '../../api/client.ts'
import { expenseApi } from '../../api/expenses.ts'
import type {
  ClaimInput,
  ExpenseClaim,
  ExpenseLink,
  ExpenseSettings,
  ExpenseTab,
} from '../../api/expenses.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageActions, Segmented } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import {
  Alert,
  Checkbox,
  EmptyState,
  Field,
  LoadError,
  Loading,
  SelectField,
} from '../../components/ui.tsx'
import { formatEuro } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ClaimEvents, ClaimFacts, ClaimFiles, ClaimForm, StatusBadge } from './ExpenseParts.tsx'
import { amountText, euro, formErrors } from './format.ts'
import { Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { expensePayChecks } from '../../learning/checks.ts'

const todayIso = () => new Date().toISOString().slice(0, 10)

/** Unterseiten unter /finanzen/auslagen */
export function ExpensesArea({ canPay }: { canPay: boolean }) {
  return (
    <Routes>
      <Route index element={<ExpensesPage />} />
      <Route path="sammelueberweisung" element={<TransfersPage canPay={canPay} />} />
      <Route path="links" element={<LinksPage />} />
      <Route path="einstellungen" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/finanzen/auslagen" replace />} />
    </Routes>
  )
}

function ExpensesPage() {
  const org = useActiveOrg()
  const view = useDetailParam('ansicht')
  const detail = useDetailParam('auslage')
  const tab = (view.value as ExpenseTab | null) ?? 'review'
  const list = useLoad(() => expenseApi.list(org.id, tab), [org.id, tab])
  const [creating, setCreating] = useState(false)
  const [picked, setPicked] = useState<number[]>([])
  const [notice, setNotice] = useState('')
  const [failure, setFailure] = useState('')
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
                <th>{t('Nummer')}</th>
                <th>{t('Von')}</th>
                <th>{t('Zweck')}</th>
                <th>{t('Betrag')}</th>
                <th>{t('Stand')}</th>
              </tr>
            </thead>
            <tbody>
              {data.claims.map((c) => (
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

function ClaimPanel({ id, onBack }: { id: number; onBack: () => void }) {
  const org = useActiveOrg()
  const load = useLoad(() => expenseApi.get(org.id, id), [org.id, id])
  const options = useLoad(() => expenseApi.options(org.id), [org.id])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [account, setAccount] = useState('')
  const [payDay, setPayDay] = useState(todayIso())
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
    } catch (err) {
      setFailure(errorMessage(err))
      await load.reload()
    } finally {
      setBusy(false)
    }
  }
  const inReview = ['submitted', 'confirmed'].includes(claim.status)
  const categories = options.data?.categories ?? []
  const accounts = options.data?.accounts ?? []
  const url = (fileId: number) => expenseApi.fileUrl(org.id, id, fileId)
  const ask = async () => {
    const text = await promptDialog({
      title: t('Rückfrage an {name}', { name: claim.name }),
      label: t('Was fehlt oder ist unklar?'),
      confirmLabel: t('Rückfrage senden'),
      danger: false,
    })
    if (text)
      await run(
        () => expenseApi.action(org.id, id, 'ask', { text, version: claim.version }),
        t('Rückfrage gesendet.'),
      )
  }
  const reject = async () => {
    const text = await promptDialog({
      title: t('Auslage {number} ablehnen?', { number: claim.number }),
      label: t('Grund (geht an die Person)'),
      confirmLabel: t('Ablehnen'),
    })
    if (text)
      await run(
        () => expenseApi.action(org.id, id, 'reject', { reason: text, version: claim.version }),
        t('Auslage abgelehnt.'),
      )
  }
  const approve = () =>
    run(
      () =>
        expenseApi.action(org.id, id, 'approve', {
          amount: amount ? amountText(amount) : undefined,
          reason,
          version: claim.version,
        }),
      claim.needs_second && !claim.approved_once
        ? t('Erste Freigabe gespeichert. Jetzt gibt eine zweite Person frei.')
        : t('Auslage freigegeben.'),
    )
  const pay = async () => {
    const chosen = accounts.find((a) => String(a.id) === account)
    const yes = await confirmDialog({
      title: t('{amount} auszahlen?', { amount: euro(claim.amount_due) }),
      message: t(
        'HUBIplan bucht die Ausgabe am {day} auf {account} und hängt die Belege an die Buchung.',
        { day: formatDate(payDay), account: chosen?.name ?? '' },
      ),
      confirmLabel: t('Auszahlen und buchen'),
      danger: false,
    })
    if (yes)
      await run(
        () =>
          expenseApi.action(org.id, id, 'pay', {
            account: Number(account),
            date: payDay,
            version: claim.version,
          }),
        t('Ausgezahlt und gebucht.'),
      )
  }
  const setCategory = (lineId: number, category: string) =>
    run(
      () =>
        expenseApi.update(org.id, id, {
          categories: { [String(lineId)]: category ? Number(category) : null },
          version: claim.version,
        }),
      t('Kategorie gespeichert.'),
    )
  const canCategorize = ['submitted', 'confirmed', 'question', 'approved'].includes(claim.status)
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
            {claim.number || t('Entwurf')} · {claim.name}
          </h2>
          <span>
            <StatusBadge claim={claim} />
            {claim.self_approved && (
              <span className="badge badge-warn">
                {claim.reviewed ? t('selbst freigegeben, gesichtet') : t('selbst freigegeben')}
              </span>
            )}
          </span>
        </div>
        <p>{claim.purpose}</p>
        {notice && <Alert kind="success">{notice}</Alert>}
        {failure && <Alert kind="error">{failure}</Alert>}
        {!!claim.hints?.length && (
          <Alert kind="info">
            <strong>{t('Bitte prüfen:')}</strong>
            <ul className="expense-items">
              {claim.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          </Alert>
        )}
        {claim.budget && <p className="muted">{claim.budget}</p>}
        {claim.needs_confirm && (
          <Alert kind="info">
            {t('Wartet auf die sachliche Bestätigung durch {unit}.', { unit: claim.confirm_unit })}
          </Alert>
        )}
        <ClaimFacts claim={claim} />
        {claim.note && (
          <p>
            <strong>{t('Begründung ohne Beleg:')}</strong> {claim.note}
          </p>
        )}
        {canCategorize && claim.kind !== 'advance' && (
          <fieldset className="stack">
            <legend>{t('Kategorien für die Buchung')}</legend>
            {claim.lines.map((line) => (
              <SelectField
                key={line.id}
                label={`${line.text || t('Betrag')} · ${euro(line.amount)}`}
                value={line.category ? String(line.category) : ''}
                disabled={busy}
                onChange={(e) => void setCategory(line.id!, e.target.value)}
              >
                <option value="">{t('bitte wählen')}</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </SelectField>
            ))}
          </fieldset>
        )}
        <h3>{t('Belege')}</h3>
        <ClaimFiles claim={claim} url={url} />
        {inReview && !claim.own && !claim.needs_confirm && (
          <fieldset className="stack">
            <legend>
              <Term k="four_eyes">{t('Freigeben')}</Term>
            </legend>
            {claim.needs_second && (
              <p className="muted small">
                {claim.approved_once
                  ? t('Die erste Freigabe liegt vor. Du gibst als zweite Person frei.')
                  : t('Ab diesem Betrag geben zwei Personen frei.')}
              </p>
            )}
            {!claim.approved_once && (
              <>
                <Field
                  label={t('Weniger freigeben (optional)')}
                  inputMode="decimal"
                  value={amount}
                  hint={t('Leer: ganzer Betrag von {sum}', { sum: euro(claim.total) })}
                  onChange={(e) => setAmount(e.target.value)}
                />
                {amount && (
                  <Field
                    label={t('Grund der Kürzung')}
                    value={reason}
                    maxLength={300}
                    onChange={(e) => setReason(e.target.value)}
                  />
                )}
              </>
            )}
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={approve}
              >
                {t('Freigeben')}
              </button>
              <button type="button" className="button" disabled={busy} onClick={ask}>
                {t('Rückfrage stellen')}
              </button>
              <button
                type="button"
                className="button button-danger"
                disabled={busy}
                onClick={reject}
              >
                {t('Ablehnen')}
              </button>
            </div>
          </fieldset>
        )}
        {inReview && claim.own && (
          <>
            {Number(claim.total) <= Number(claim.self_limit ?? 0) && !claim.needs_second ? (
              <fieldset className="stack">
                <legend>{t('Eigene Auslage')}</legend>
                <p className="muted small">
                  {t(
                    'Bis {limit} darfst du deine eigene Auslage selbst freigeben. Eine zweite Person sichtet sie nachträglich.',
                    { limit: euro(claim.self_limit) },
                  )}
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={busy}
                    onClick={approve}
                  >
                    {t('Selbst freigeben')}
                  </button>
                </div>
              </fieldset>
            ) : (
              <>
                <Alert kind="info">{t('Deine eigene Auslage gibt eine andere Person frei.')}</Alert>
                <Why k="expense_own" />
              </>
            )}
          </>
        )}
        {claim.status === 'question' && (
          <div className="button-row">
            <button type="button" className="button button-danger" disabled={busy} onClick={reject}>
              {t('Ablehnen')}
            </button>
          </div>
        )}
        {claim.status === 'draft' && claim.source === 'treasury' && (
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                void run(() => expenseApi.action(org.id, id, 'submit'), t('Auslage eingereicht.'))
              }
            >
              {t('Einreichen')}
            </button>
          </div>
        )}
        {claim.status === 'approved' && (
          <fieldset className="stack">
            <legend>{t('Auszahlen')}</legend>
            {claim.epc && claim.payout === 'bank' && (
              <div className="stack">
                <p className="muted small">
                  {t('GiroCode für die Banking-App, oder gesammelt über die Sammelüberweisung.')}
                </p>
                <div className="expense-girocode">
                  <QRCodeSVG value={claim.epc} size={180} marginSize={2} title={t('GiroCode')} />
                </div>
              </div>
            )}
            <SelectField
              label={claim.payout === 'cash' ? t('Aus Kasse') : t('Von Konto')}
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            >
              <option value="">{t('bitte wählen')}</option>
              {accounts
                .filter((a) => (claim.payout === 'cash' ? a.kind === 'cash' : a.kind !== 'cash'))
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </SelectField>
            <Field
              label={t('Datum der Zahlung')}
              type="date"
              value={payDay}
              onChange={(e) => setPayDay(e.target.value)}
            />
            <Checklist
              title={t('Vor dem Auszahlen')}
              items={expensePayChecks({
                kind: claim.kind,
                fileCount: claim.file_count,
                linesWithoutCategory: claim.lines.filter((l) => l.category === null).length,
                invoiceTo: claim.invoice_to,
                payout: claim.payout,
                hasIban: !!claim.payee?.iban,
                selfApproved: claim.self_approved,
                reviewed: claim.reviewed,
              })}
            />
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy || !account}
                onClick={pay}
              >
                {t('Ausgezahlt: buchen')}
              </button>
              <button
                type="button"
                className="button button-danger"
                disabled={busy}
                onClick={reject}
              >
                {t('Ablehnen')}
              </button>
            </div>
          </fieldset>
        )}
        {claim.self_approved && !claim.reviewed && !claim.own && (
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() =>
                void run(() => expenseApi.review(org.id, [id]), t('Als gesichtet markiert.'))
              }
            >
              {t('Nachträglich gesichtet')}
            </button>
          </div>
        )}
        <ClaimEvents claim={claim} />
      </section>
    </div>
  )
}

function TransfersPage({ canPay }: { canPay: boolean }) {
  const org = useActiveOrg()
  const load = useLoad(() => expenseApi.transfers(org.id), [org.id])
  const [picked, setPicked] = useState<number[]>([])
  const [bank, setBank] = useState('')
  const [day, setDay] = useState(todayIso())
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  const data = load.data
  if (!data) return <Loading />
  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setFailure('')
    setNotice('')
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
  const sum = data.ready
    .filter((r) => picked.includes(r.id))
    .reduce((s, r) => s + Number(r.amount), 0)
  return (
    <div className="stack">
      <p>
        {t(
          'Freigegebene Auslagen mit Bankverbindung gesammelt überweisen: HUBIplan erstellt eine SEPA-Datei (pain.001) für das Onlinebanking. Beim ersten Herunterladen bucht HUBIplan jede Auslage als Ausgabe am Ausführungstag.',
        )}
      </p>
      {notice && <Alert kind="success">{notice}</Alert>}
      {failure && <Alert kind="error">{failure}</Alert>}
      {!canPay && (
        <Alert kind="info">{t('Zum Auszahlen fehlt das Recht, die Kasse zu führen.')}</Alert>
      )}
      <section className="card stack">
        <h2>{t('Bereit zur Überweisung')}</h2>
        {!data.ready.length ? (
          <p className="muted">{t('Gerade wartet keine Auslage auf eine Überweisung.')}</p>
        ) : (
          <>
            {data.ready.map((r) => (
              <Checkbox
                key={r.id}
                label={`${r.number} · ${r.name} · ${euro(r.amount)} · ${r.holder} ${r.iban}`}
                hint={r.categories_ok ? r.purpose : t('Kategorie fehlt noch')}
                checked={picked.includes(r.id)}
                disabled={!r.categories_ok || !canPay}
                onChange={(on) =>
                  setPicked(on ? [...picked, r.id] : picked.filter((i) => i !== r.id))
                }
              />
            ))}
            <SelectField
              label={t('Von Konto')}
              value={bank}
              onChange={(e) => setBank(e.target.value)}
            >
              <option value="">{t('bitte wählen')}</option>
              {data.banks.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Ausführungstag')}
              type="date"
              value={day}
              min={todayIso()}
              onChange={(e) => setDay(e.target.value)}
            />
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy || !picked.length || !bank || !canPay}
                onClick={() =>
                  void run(async () => {
                    await expenseApi.createTransfer(org.id, {
                      bank_account: Number(bank),
                      execution_date: day,
                      claims: picked,
                    })
                    setPicked([])
                  }, t('Sammelüberweisung angelegt. Jetzt die Datei herunterladen.'))
                }
              >
                {t('Sammelüberweisung anlegen ({sum})', { sum: formatEuro(sum) })}
              </button>
            </div>
          </>
        )}
      </section>
      {data.runs.length > 0 && (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('Angelegt')}</th>
                <th>{t('Ausführung')}</th>
                <th>{t('Auslagen')}</th>
                <th>{t('Summe')}</th>
                <th>{t('Stand')}</th>
                <th>{t('Aktionen')}</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((run_) => (
                <tr key={run_.id}>
                  <td>{formatDate(run_.created_at)}</td>
                  <td>{formatDate(run_.execution_date)}</td>
                  <td>{run_.items.map((i) => i.number).join(', ')}</td>
                  <td>{euro(run_.total)}</td>
                  <td>
                    {run_.cancelled
                      ? t('aufgehoben')
                      : run_.exported
                        ? t('heruntergeladen und gebucht')
                        : t('bereit')}
                  </td>
                  <td>
                    {!run_.cancelled && canPay && (
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            const blob = await expenseApi.exportTransfer(org.id, run_.id)
                            saveBlob(blob, `auslagen-${run_.reference}.xml`)
                          }, t('Datei heruntergeladen. Bitte im Onlinebanking hochladen.'))
                        }
                      >
                        {t('Datei herunterladen')}
                      </button>
                    )}
                    {!run_.cancelled && !run_.exported && canPay && (
                      <button
                        type="button"
                        className="button button-ghost"
                        disabled={busy}
                        onClick={() =>
                          void run(
                            () => expenseApi.cancelTransfer(org.id, run_.id),
                            t('Sammelüberweisung aufgehoben.'),
                          )
                        }
                      >
                        {t('Aufheben')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function LinksPage() {
  const org = useActiveOrg()
  const load = useLoad(() => expenseApi.links(org.id), [org.id])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [days, setDays] = useState('30')
  const [created, setCreated] = useState<ExpenseLink | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  if (!load.data) return <Loading />
  const create = async () => {
    setBusy(true)
    setFailure('')
    try {
      setCreated(await expenseApi.createLink(org.id, { name, email, days: Number(days) || 30 }))
      setName('')
      setEmail('')
      await load.reload()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="stack">
      <p>
        {t(
          'Helfer, Eltern oder Mitglieder ohne Zugang reichen Auslagen über einen persönlichen Link ein. Er gilt höchstens 90 Tage und lässt sich jederzeit widerrufen. Einschalten unter Einstellungen.',
        )}
      </p>
      {failure && <Alert kind="error">{failure}</Alert>}
      {created?.url && (
        <Alert kind="success">
          {t('Link für {name} (nur jetzt sichtbar, bitte weitergeben):', { name: created.name })}{' '}
          <code className="break-all">{created.url}</code>
        </Alert>
      )}
      <section className="card stack">
        <h2>{t('Neuer Link')}</h2>
        <Field
          label={t('Name')}
          value={name}
          maxLength={200}
          onChange={(e) => setName(e.target.value)}
        />
        <Field
          label={t('E-Mail für Bescheide (optional)')}
          type="email"
          value={email}
          maxLength={254}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label={t('Gültig für Tage')}
          type="number"
          min={1}
          max={90}
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
        <div className="button-row">
          <button type="button" className="button button-primary" disabled={busy} onClick={create}>
            {t('Link ausstellen')}
          </button>
        </div>
      </section>
      {load.data.links.length > 0 && (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('Name')}</th>
                <th>{t('Gültig bis')}</th>
                <th>{t('Zuletzt genutzt')}</th>
                <th>{t('Aktionen')}</th>
              </tr>
            </thead>
            <tbody>
              {load.data.links.map((l) => (
                <tr key={l.id}>
                  <td>{l.name}</td>
                  <td>{l.revoked ? t('widerrufen') : formatDate(l.valid_until)}</td>
                  <td>{l.used_at ? formatDate(l.used_at) : '—'}</td>
                  <td>
                    {!l.revoked && (
                      <button
                        type="button"
                        className="button button-ghost"
                        onClick={async () => {
                          if (
                            await confirmDialog({
                              final: true,
                              title: t('Link für {name} widerrufen?', { name: l.name }),
                              confirmLabel: t('Widerrufen'),
                            })
                          ) {
                            await expenseApi.revokeLink(org.id, l.id)
                            await load.reload()
                          }
                        }}
                      >
                        {t('Widerrufen')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SettingsPage() {
  const org = useActiveOrg()
  const load = useLoad(() => expenseApi.settings(org.id), [org.id])
  if (load.error) return <LoadError message={load.error} onRetry={load.reload} />
  if (!load.data) return <Loading />
  return <SettingsForm key={JSON.stringify(load.data)} value={load.data} onSaved={load.reload} />
}

function SettingsForm({ value, onSaved }: { value: ExpenseSettings; onSaved: () => void }) {
  const org = useActiveOrg()
  const [v, setV] = useState(value)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  const edit = v.can_edit
  const set = <K extends keyof ExpenseSettings>(key: K, val: ExpenseSettings[K]) =>
    setV({ ...v, [key]: val })
  const save = async () => {
    setBusy(true)
    setFailure('')
    setNotice('')
    try {
      await expenseApi.saveSettings(org.id, {
        submitters: v.submitters,
        self_limit: amountText(v.self_limit) || '0',
        second_from: v.second_from ? amountText(v.second_from) : null,
        hint_months: Number(v.hint_months),
        confirm_departments: v.confirm_departments,
        mileage_enabled: v.mileage_enabled,
        km_rate: amountText(v.km_rate) || '0',
        advances_enabled: v.advances_enabled,
        links_enabled: v.links_enabled,
        waiver_basis: v.waiver_basis,
        waiver_basis_date: v.waiver_basis_date || null,
      })
      setNotice(t('Gespeichert.'))
      onSaved()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      {notice && <Alert kind="success">{notice}</Alert>}
      {failure && <Alert kind="error">{failure}</Alert>}
      {!edit && <Alert kind="info">{t('Ändern dürfen nur Personen, die die Kasse führen.')}</Alert>}
      <SelectField
        label={t('Wer darf Auslagen melden?')}
        value={v.submitters}
        disabled={!edit}
        onChange={(e) => set('submitters', e.target.value as ExpenseSettings['submitters'])}
      >
        <option value="members">{t('alle aktiven Mitglieder mit Zugang')}</option>
        <option value="officers">{t('nur Personen mit Amt oder Rolle')}</option>
      </SelectField>
      <Field
        label={t('Eigene Auslagen der Kasse selbst freigeben bis (€)')}
        inputMode="decimal"
        value={v.self_limit}
        disabled={!edit}
        hint={t('0 schaltet das aus. Eine zweite Person sichtet nachträglich.')}
        onChange={(e) => set('self_limit', e.target.value)}
      />
      <Field
        label={t('Zwei Freigaben ab (€, optional)')}
        inputMode="decimal"
        value={v.second_from ?? ''}
        disabled={!edit}
        onChange={(e) => set('second_from', e.target.value || null)}
      />
      <Why k="expense_second_approval" />
      <Field
        label={t('Hinweis bei Käufen älter als (Monate)')}
        type="number"
        min={0}
        max={36}
        value={String(v.hint_months)}
        disabled={!edit}
        onChange={(e) => set('hint_months', Number(e.target.value))}
      />
      {v.departments.length > 0 && (
        <fieldset className="stack">
          <legend>{t('Sachliche Bestätigung durch die Leitung der Untereinheit')}</legend>
          <p className="muted small">
            {t(
              'Auslagen für diese Untereinheiten (und darunter) bestätigt zuerst deren Leitung, bevor die Kasse freigibt.',
            )}
          </p>
          {v.departments.map((d) => (
            <Checkbox
              key={d.id}
              label={d.name}
              disabled={!edit}
              checked={v.confirm_departments.includes(d.id)}
              onChange={(on) =>
                set(
                  'confirm_departments',
                  on
                    ? [...v.confirm_departments, d.id]
                    : v.confirm_departments.filter((i) => i !== d.id),
                )
              }
            />
          ))}
        </fieldset>
      )}
      <Why k="expense_mileage" />
      <Checkbox
        label={t('Fahrtkosten nach Kilometern')}
        checked={v.mileage_enabled}
        disabled={!edit}
        onChange={(on) => set('mileage_enabled', on)}
      />
      {v.mileage_enabled && (
        <Field
          label={t('Satz je Kilometer (€)')}
          term="mileage_rate"
          inputMode="decimal"
          value={v.km_rate}
          disabled={!edit}
          hint={t('Steuerfrei bis 0,30 € je km (Pkw).')}
          onChange={(e) => set('km_rate', e.target.value)}
        />
      )}
      <Checkbox
        label={t('Vorschüsse vor dem Kauf')}
        checked={v.advances_enabled}
        disabled={!edit}
        onChange={(on) => set('advances_enabled', on)}
      />
      <Checkbox
        label={t('Links für Personen ohne Zugang')}
        checked={v.links_enabled}
        disabled={!edit}
        onChange={(on) => set('links_enabled', on)}
      />
      {v.donations_enabled && (
        <fieldset className="stack">
          <legend>{t('Verzicht als Spende (Aufwandsspende)')}</legend>
          <Why k="donation_waiver" />
          <p className="muted small">
            {t(
              'Nur mit einem Anspruch auf Erstattung, der vorher festgelegt war (Satzung, Vorstandsbeschluss oder Vertrag). Ohne Angabe gibt es keinen Verzicht.',
            )}
          </p>
          <Field
            label={t('Grundlage des Erstattungsanspruchs')}
            value={v.waiver_basis}
            maxLength={300}
            disabled={!edit}
            onChange={(e) => set('waiver_basis', e.target.value)}
          />
          <Field
            label={t('Datum der Grundlage')}
            type="date"
            value={v.waiver_basis_date ?? ''}
            disabled={!edit}
            onChange={(e) => set('waiver_basis_date', e.target.value || null)}
          />
        </fieldset>
      )}
      {edit && (
        <div className="button-row">
          <button type="button" className="button button-primary" disabled={busy} onClick={save}>
            {t('Speichern')}
          </button>
        </div>
      )}
    </section>
  )
}
