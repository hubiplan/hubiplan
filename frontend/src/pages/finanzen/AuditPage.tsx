// Finanzen › Jahresabschluss › Kassenprüfung: Prüfauftrag je Geschäftsjahr,
// Stichproben, Kontenabgleich, Prüfpunkte und Prüfbericht (Konzept vereinskasse-steuern, S6).
// Die Kasse legt den Auftrag an; abhaken dürfen nur Kassenprüfer (Kasse lesen, nicht führen).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { euro, financeApi } from '../../api/finance.ts'
import type {
  AuditRecommendation,
  AuditResult,
  CashAudit,
  CashAuditAccount,
  CashAuditSample,
} from '../../api/finance.ts'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { auditCloseChecks } from '../../learning/checks.ts'
import { t } from '../../i18n/index.ts'

function resultOptions(): { value: AuditResult; label: string }[] {
  return [
    { value: '', label: t('offen') },
    { value: 'ok', label: t('in Ordnung') },
    { value: 'issue', label: t('Rückfrage') },
    { value: 'na', label: t('entfällt') },
  ]
}

function recommendationOptions(): { value: AuditRecommendation; label: string }[] {
  return [
    { value: '', label: t('noch offen') },
    { value: 'discharge', label: t('Entlastung empfohlen') },
    { value: 'notes', label: t('Entlastung mit Anmerkungen empfohlen') },
    { value: 'refuse', label: t('Entlastung nicht empfohlen') },
  ]
}

function NewAudit({
  years,
  taken,
  onDone,
}: {
  years: { year: number; label: string }[]
  taken: number[]
  onDone: (audit: CashAudit | null) => void
}) {
  const org = useActiveOrg()
  const free = years.filter((y) => !taken.includes(y.year))
  const form = useForm({
    year: String(free[1]?.year ?? free[0]?.year ?? ''),
    auditors: '',
    due_on: '',
    sample_size: '20',
  })
  const { values: v, errors, set } = form

  async function save(e: FormEvent) {
    e.preventDefault()
    const saved = await form.submit(() =>
      financeApi.createAudit(org.id, {
        year: Number(v.year),
        auditors: v.auditors,
        due_on: v.due_on || null,
        sample_size: Number(v.sample_size) || 20,
      }),
    )
    if (saved) onDone(saved as CashAudit)
  }

  return (
    <form className="card card-wide" onSubmit={(e) => void save(e)}>
      <h3>{t('Neuer Prüfauftrag')}</h3>
      <fieldset disabled={form.busy}>
        <div className="grid-2">
          <SelectField
            label={t('Geschäftsjahr')}
            value={v.year}
            error={errors.year}
            onChange={(e) => set('year', e.target.value)}
          >
            {free.map((y) => (
              <option key={y.year} value={y.year}>
                {y.label}
              </option>
            ))}
          </SelectField>
          <Field
            label={t('Namen der Kassenprüfer')}
            value={v.auditors}
            error={errors.auditors}
            placeholder={t('z. B. Erika Musterfrau, Max Mustermann')}
            onChange={(e) => set('auditors', e.target.value)}
          />
          <Field
            label={t('Zu prüfen bis (optional)')}
            type="date"
            value={v.due_on}
            error={errors.due_on}
            onChange={(e) => set('due_on', e.target.value)}
          />
          <Field
            label={t('Stichproben')}
            type="number"
            min={1}
            max={200}
            value={v.sample_size}
            error={errors.sample_size}
            hint={t('Die größten Ausgaben und zufällig gezogene weitere Buchungen')}
            onChange={(e) => set('sample_size', e.target.value)}
          />
        </div>
      </fieldset>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy || !v.year}>
          {t('Prüfauftrag anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function SettingsCard({ audit, onSaved }: { audit: CashAudit; onSaved: (a: CashAudit) => void }) {
  const org = useActiveOrg()
  const meetings = useLoad(() => financeApi.auditMeetings(org.id), [org.id])
  const form = useForm({
    auditors: audit.auditors,
    due_on: audit.due_on ?? '',
    meeting: String(audit.meeting ?? ''),
  })
  const { values: v, errors, set } = form

  async function save(e: FormEvent) {
    e.preventDefault()
    const saved = await form.submit(() =>
      financeApi.updateAudit(org.id, audit.id, {
        auditors: v.auditors,
        due_on: v.due_on || null,
        meeting: v.meeting ? Number(v.meeting) : null,
      }),
    )
    if (saved) onSaved(saved as CashAudit)
  }

  return (
    <form className="card card-wide" onSubmit={(e) => void save(e)}>
      <h3>{t('Prüfauftrag')}</h3>
      <fieldset disabled={form.busy}>
        <div className="grid-2">
          <Field
            label={t('Namen der Kassenprüfer')}
            value={v.auditors}
            error={errors.auditors}
            onChange={(e) => set('auditors', e.target.value)}
          />
          <Field
            label={t('Zu prüfen bis (optional)')}
            type="date"
            value={v.due_on}
            error={errors.due_on}
            onChange={(e) => set('due_on', e.target.value)}
          />
          {(meetings.data?.length ?? 0) > 0 && (
            <SelectField
              label={t('Für die Versammlung (optional)')}
              value={v.meeting}
              error={errors.meeting}
              onChange={(e) => set('meeting', e.target.value)}
            >
              <option value="">{t('keine')}</option>
              {meetings.data?.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} ({formatDate(m.date)})
                </option>
              ))}
            </SelectField>
          )}
        </div>
      </fieldset>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Speichern')}
        </button>
      </div>
    </form>
  )
}

function AccountRow({
  row,
  canAudit,
  onSave,
}: {
  row: CashAuditAccount
  canAudit: boolean
  onSave: (data: Record<string, unknown>) => Promise<boolean>
}) {
  const [stated, setStated] = useState((row.statement_balance ?? '').replace('.', ','))
  const [note, setNote] = useState(row.note)
  const changed = stated !== (row.statement_balance ?? '').replace('.', ',') || note !== row.note
  return (
    <tr>
      <td>{row.name}</td>
      <td className="num">{euro(row.book_balance)}</td>
      <td className="num">
        {canAudit ? (
          <input
            aria-label={t('Nachweis für {name}', { name: row.name })}
            inputMode="decimal"
            value={stated}
            onChange={(e) => setStated(e.target.value)}
          />
        ) : row.statement_balance !== null ? (
          euro(row.statement_balance)
        ) : (
          '–'
        )}
      </td>
      <td className="num">
        {row.difference === null ? (
          '–'
        ) : Number(row.difference) !== 0 ? (
          <strong>{euro(row.difference)}</strong>
        ) : (
          euro(row.difference)
        )}
      </td>
      <td>
        {canAudit ? (
          <input
            aria-label={t('Anmerkung zu {name}', { name: row.name })}
            value={note}
            maxLength={300}
            onChange={(e) => setNote(e.target.value)}
          />
        ) : (
          row.note
        )}
        {row.checked_by && <div className="muted small">{row.checked_by}</div>}
      </td>
      <td>
        {canAudit && changed && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              void onSave({ account: row.id, statement_balance: stated.trim() || null, note })
            }
          >
            {t('Speichern')}
          </button>
        )}
      </td>
    </tr>
  )
}

function SampleRow({
  row,
  canAudit,
  onSave,
}: {
  row: CashAuditSample
  canAudit: boolean
  onSave: (data: Record<string, unknown>) => Promise<boolean>
}) {
  const org = useActiveOrg()
  const [note, setNote] = useState(row.note)
  return (
    <tr>
      <td>
        {row.number}
        <div className="muted small">{formatDate(row.date)}</div>
      </td>
      <td>
        {row.text}
        <div className="muted small">
          {[row.counterparty, row.category, row.account].filter(Boolean).join(' · ')}
        </div>
      </td>
      <td className="num">
        {row.kind === 'expense' ? '−' : ''}
        {euro(row.amount)}
      </td>
      <td>
        {row.receipts.length === 0 ? (
          <span className="badge badge-open">{t('kein Beleg')}</span>
        ) : (
          row.receipts.map((r) => (
            <div key={r.id}>
              <a href={financeApi.receiptUrl(org.id, r.id)} target="_blank" rel="noreferrer">
                {r.name}
              </a>
            </div>
          ))
        )}
      </td>
      <td>
        {canAudit ? (
          <>
            <select
              aria-label={t('Ergebnis zu {n}', { n: row.number })}
              value={row.result}
              onChange={(e) => void onSave({ sample: row.id, result: e.target.value, note })}
            >
              {resultOptions()
                .filter((o) => o.value !== 'na')
                .map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
            </select>
            <input
              aria-label={t('Anmerkung zu {n}', { n: row.number })}
              value={note}
              maxLength={300}
              placeholder={t('Anmerkung')}
              onChange={(e) => setNote(e.target.value)}
              onBlur={() => {
                if (note !== row.note) void onSave({ sample: row.id, result: row.result, note })
              }}
            />
          </>
        ) : (
          <>
            {resultOptions().find((o) => o.value === row.result)?.label}
            {row.note && <div className="small">{row.note}</div>}
          </>
        )}
        {row.checked_by && <div className="muted small">{row.checked_by}</div>}
      </td>
    </tr>
  )
}

function ChecksCard({
  audit,
  canAudit,
  onSaved,
}: {
  audit: CashAudit
  canAudit: boolean
  onSaved: (a: CashAudit) => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    checks: Object.fromEntries(
      audit.checks.map((c) => [c.key, { result: c.result, note: c.note }]),
    ),
    findings: audit.findings,
    recommendation: audit.recommendation as string,
  })
  const { values: v, errors, set } = form

  function setCheck(key: string, field: 'result' | 'note', value: string) {
    set('checks', { ...v.checks, [key]: { ...v.checks[key], [field]: value } })
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    const saved = await form.submit(() =>
      financeApi.updateAudit(org.id, audit.id, {
        checks: v.checks,
        findings: v.findings,
        recommendation: v.recommendation,
      }),
    )
    if (saved) onSaved(saved as CashAudit)
  }

  return (
    <form className="card card-wide" onSubmit={(e) => void save(e)}>
      <h3>{t('Prüfpunkte und Ergebnis')}</h3>
      <p className="muted small">
        {t('Die Empfehlung richtet sich an die Versammlung, die über die')}{' '}
        <Term k="discharge">{t('Entlastung')}</Term> {t('des Vorstands abstimmt.')}
      </p>
      <Why k="audit_recommendation" />
      <fieldset disabled={!canAudit || form.busy}>
        <table className="table">
          <tbody>
            {audit.checks.map((c) => (
              <tr key={c.key}>
                <td>{c.label}</td>
                <td>
                  <select
                    aria-label={c.label}
                    value={v.checks[c.key]?.result ?? ''}
                    onChange={(e) => setCheck(c.key, 'result', e.target.value)}
                  >
                    {resultOptions().map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    aria-label={t('Anmerkung zu {name}', { name: c.label })}
                    value={v.checks[c.key]?.note ?? ''}
                    maxLength={300}
                    onChange={(e) => setCheck(c.key, 'note', e.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <label className="field">
          <span>{t('Feststellungen')}</span>
          <textarea
            rows={4}
            value={v.findings}
            maxLength={5000}
            onChange={(e) => set('findings', e.target.value)}
          />
        </label>
        <SelectField
          label={t('Empfehlung zur Entlastung')}
          value={v.recommendation}
          error={errors.recommendation}
          onChange={(e) => set('recommendation', e.target.value)}
        >
          {recommendationOptions().map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </SelectField>
      </fieldset>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      {canAudit && (
        <div className="button-row">
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Speichern')}
          </button>
        </div>
      )}
    </form>
  )
}

function AuditDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const org = useActiveOrg()
  const loaded = useLoad(() => financeApi.audit(org.id, id), [org.id, id])
  const [fresh, setFresh] = useState<CashAudit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const audit = fresh?.id === id ? fresh : loaded.data

  if (loaded.error) return <Alert kind="error">{loaded.error}</Alert>
  if (!audit) return <Loading />
  const open = audit.status === 'open'
  const canAudit = audit.can_audit && open
  const manage = audit.can_manage && open

  async function run(action: () => Promise<CashAudit>): Promise<boolean> {
    setError(null)
    try {
      setFresh(await action())
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    }
  }

  async function close() {
    const ok = await confirmDialog({
      title: t('Prüfung abschließen?'),
      message: t(
        'Danach lässt sich nichts mehr abhaken. Der Prüfbericht steht als PDF bereit; wieder öffnen geht nur mit Grund.',
      ),
      confirmLabel: t('Abschließen'),
    })
    if (ok) await run(() => financeApi.closeAudit(org.id, audit!.id))
  }

  async function reopen() {
    const reason = await promptDialog({
      title: t('Prüfung wieder öffnen?'),
      label: t('Grund'),
      confirmLabel: t('Wieder öffnen'),
    })
    if (reason) await run(() => financeApi.reopenAudit(org.id, audit!.id, reason))
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Prüfauftrag löschen?'),
      message: t('Der Prüfauftrag {y} wird gelöscht.', { y: audit!.label }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await financeApi.deleteAudit(org.id, audit!.id)
      onBack()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const f = audit.facts
  return (
    <div className="stack" data-testid="audit-detail">
      <div className="card card-wide filters">
        <button type="button" className="button button-ghost" onClick={onBack}>
          {t('Zurück zur Übersicht')}
        </button>
        <strong>{t('Kassenprüfung {y}', { y: audit.label })}</strong>
        <span className="muted">{audit.status_label}</span>
        <span className="button-row push-right">
          <a
            className="button button-ghost"
            href={financeApi.auditPdfUrl(org.id, audit.id)}
            target="_blank"
            rel="noreferrer"
          >
            {t('Prüfbericht (PDF)')}
          </a>
          {canAudit && (
            <button type="button" className="button button-primary" onClick={() => void close()}>
              {t('Prüfung abschließen')}
            </button>
          )}
          {!open && (audit.can_audit || audit.can_manage) && (
            <button type="button" className="button button-ghost" onClick={() => void reopen()}>
              {t('Wieder öffnen')}
            </button>
          )}
          {manage && (
            <button type="button" className="button button-ghost" onClick={() => void remove()}>
              {t('Löschen')}
            </button>
          )}
        </span>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {open && !audit.can_audit && (
        <Alert kind="info">
          {t(
            'Abhaken dürfen nur die Kassenprüfer: ein Konto mit „Kasse lesen“, aber ohne „Kasse führen“.',
          )}
        </Alert>
      )}
      {manage && <SettingsCard audit={audit} onSaved={setFresh} />}
      {!manage && (
        <div className="card card-wide">
          <p>
            {t('Prüfer')}: {audit.auditors || '–'}
            {audit.due_on && ` · ${t('zu prüfen bis {d}', { d: formatDate(audit.due_on) })}`}
            {audit.meeting_title && ` · ${audit.meeting_title}`}
          </p>
        </div>
      )}
      <div className="card card-wide">
        <h3>{t('Zugang für die Prüfer')}</h3>
        {audit.access.length === 0 ? (
          <Alert kind="info">
            {t(
              'Noch hat niemand Prüferrechte. Gib den Kassenprüfern unter Einstellungen › Rollen und Rechte eine Rolle mit „Kasse lesen“ (ohne „Kasse führen“), am besten mit Enddatum.',
            )}{' '}
            <Link to="/einstellungen/rollen">{t('Zu den Rollen')}</Link>
          </Alert>
        ) : (
          <ul>
            {audit.access.map((a) => (
              <li key={a.name}>
                {a.name}
                {' · '}
                {a.until
                  ? t('Zugang bis {d}', { d: formatDate(a.until) })
                  : t('Zugang ohne Enddatum')}
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">
          {t('{n} Buchungen, davon {m} ohne Beleg. Nummernlücken: {g}.', {
            n: f.bookings,
            m: f.without_receipt,
            g: f.gap_count,
          })}{' '}
          {f.closed ? t('Jahresabschluss erstellt.') : t('Jahresabschluss noch nicht erstellt.')}{' '}
          {t('Zählprotokolle im Jahr: {n}.', { n: f.cash_counts })}
        </p>
        {f.gaps.length > 0 && (
          <p className="muted small">{t('Lücken: {list}', { list: f.gaps.join(', ') })}</p>
        )}
      </div>
      <div className="card card-wide">
        <h3>{t('Kontenabgleich zum Jahresende')}</h3>
        <Why k="audit_reconcile" />
        <p className="muted small">
          {t('Bestand laut Kassenbuch gegen Kontoauszug bzw. Zählung der Barkasse.')}
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>{t('Konto')}</th>
              <th className="num">{t('Kassenbuch')}</th>
              <th className="num">{t('Nachweis')}</th>
              <th className="num">{t('Differenz')}</th>
              <th>{t('Anmerkung')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {audit.accounts.map((row) => (
              <AccountRow
                key={`${row.id}-${row.statement_balance}-${row.note}`}
                row={row}
                canAudit={canAudit}
                onSave={(data) => run(() => financeApi.auditCheck(org.id, audit.id, data))}
              />
            ))}
          </tbody>
        </table>
      </div>
      <div className="card card-wide">
        <div className="filters">
          <h3>{t('Stichproben ({n})', { n: audit.samples.length })}</h3>
          <Why k="audit_samples" />
          {open && (audit.can_audit || audit.can_manage) && (
            <button
              type="button"
              className="button button-ghost push-right"
              onClick={() => void run(() => financeApi.auditDraw(org.id, audit.id, 5))}
            >
              {t('5 weitere ziehen')}
            </button>
          )}
        </div>
        {audit.samples.length === 0 ? (
          <p className="muted">{t('Im Geschäftsjahr gibt es keine Buchungen.')}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Buchung')}</th>
                <th>{t('Text')}</th>
                <th className="num">{t('Betrag')}</th>
                <th>{t('Beleg')}</th>
                <th>{t('Ergebnis')}</th>
              </tr>
            </thead>
            <tbody>
              {audit.samples.map((row) => (
                <SampleRow
                  key={`${row.id}-${row.result}-${row.note}`}
                  row={row}
                  canAudit={canAudit}
                  onSave={(data) => run(() => financeApi.auditCheck(org.id, audit.id, data))}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
      {canAudit && (
        <div className="card card-wide">
          <Checklist title={t('Vor dem Abschluss der Prüfung')} items={auditCloseChecks(audit)} />
        </div>
      )}
      <ChecksCard
        key={`${audit.id}-${audit.status}-${audit.recommendation}`}
        audit={audit}
        canAudit={canAudit}
        onSaved={setFresh}
      />
    </div>
  )
}

export function AuditPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  const audits = useLoad(() => financeApi.audits(org.id), [org.id])
  const [creating, setCreating] = useState(false)
  const selected = Number(params.get('pruefung') ?? '') || null

  function select(id: number | null) {
    setParams(id ? { pruefung: String(id) } : {}, { replace: false })
    if (!id) audits.reload()
  }

  if (selected) return <AuditDetail id={selected} onBack={() => select(null)} />
  const loadError = settings.error ?? audits.error
  if (loadError) return <Alert kind="error">{loadError}</Alert>
  if (!settings.data || !audits.data) return <Loading />

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Kassenprüfung')}</h2>
      <p className="muted small">
        {t(
          'Die Kasse legt je Geschäftsjahr einen Prüfauftrag an. Die Kassenprüfer haken Stichproben und Kontenstände ab, halten Feststellungen fest und empfehlen die Entlastung. Daraus entsteht der Prüfbericht.',
        )}
      </p>
      {canEdit && !creating && (
        <div className="button-row">
          <button type="button" className="button button-primary" onClick={() => setCreating(true)}>
            {t('Prüfauftrag anlegen')}
          </button>
        </div>
      )}
      {creating && (
        <NewAudit
          years={settings.data.years}
          taken={audits.data.map((a) => a.year)}
          onDone={(audit) => {
            setCreating(false)
            if (audit) select(audit.id)
          }}
        />
      )}
      <div className="card card-wide">
        {audits.data.length === 0 ? (
          <p className="muted">{t('Noch keine Kassenprüfung angelegt.')}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Geschäftsjahr')}</th>
                <th>{t('Prüfer')}</th>
                <th>{t('Stand')}</th>
                <th>{t('Empfehlung')}</th>
              </tr>
            </thead>
            <tbody>
              {audits.data.map((a) => (
                <tr key={a.id}>
                  <td>
                    <button type="button" className="link-button" onClick={() => select(a.id)}>
                      {a.label}
                    </button>
                  </td>
                  <td>{a.auditors || '–'}</td>
                  <td>
                    {a.status_label}
                    {a.status === 'open' && (
                      <div className="muted small">
                        {t('{n} Punkte offen', { n: a.open_points })}
                        {a.due_on && ` · ${t('bis {d}', { d: formatDate(a.due_on) })}`}
                      </div>
                    )}
                  </td>
                  <td>{a.recommendation_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
