import { useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { expenseApi } from '../../api/expenses.ts'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { ClaimEvents, ClaimFacts, ClaimFiles, StatusBadge } from './ExpenseParts.tsx'
import { amountText, euro } from './format.ts'
import { Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { expensePayChecks } from '../../learning/checks.ts'
import { todayIso } from './expensesHelpers.ts'

export function ClaimPanel({ id, onBack }: { id: number; onBack: () => void }) {
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
