import { useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { expenseApi } from '../../api/expenses.ts'
import type { ExpenseLink, ExpenseSettings } from '../../api/expenses.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { formatEuro } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { amountText, euro } from './format.ts'
import { Why } from '../../learning/Aids.tsx'
import { ExpensesPage } from './ExpensesPage.tsx'
import { todayIso } from './expensesHelpers.ts'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'

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

function TransfersPage({ canPay }: { canPay: boolean }) {
  const org = useActiveOrg()
  const load = useLoad(() => expenseApi.transfers(org.id), [org.id])
  const [picked, setPicked] = useState<number[]>([])
  const [bank, setBank] = useState('')
  const [day, setDay] = useState(todayIso())
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  const runSearch = useRowSearch(
    load.data?.runs ?? [],
    (r) => `${formatDate(r.created_at)} ${r.items.map((i) => i.number).join(' ')} ${r.reference}`,
    t('Sammelüberweisungen'),
  )
  const runSort = useRowSort(runSearch.shown, {
    created: (r) => r.created_at,
    execution: (r) => r.execution_date,
    total: (r) => Number(r.total),
  })
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
          {runSearch.field}
          <table>
            <thead>
              <tr>
                {runSort.head('created', t('Angelegt'))}
                {runSort.head('execution', t('Ausführung'))}
                <th>{t('Auslagen')}</th>
                {runSort.head('total', t('Summe'))}
                <th>{t('Stand')}</th>
                <th>{t('Aktionen')}</th>
              </tr>
            </thead>
            <tbody>
              {runSort.rows.map((run_) => (
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
