// Finanzen › Auswerten & abschließen › Haushaltsplan: geplante Einnahmen und Ausgaben je
// Kategorie (auf Wunsch je Untereinheit) mit Ist, Abweichung und Hochrechnung.
import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import type {
  BudgetKind,
  BudgetLine,
  BudgetLineInput,
  BudgetReport,
  BudgetTotals,
  Category,
} from '../../api/finance.ts'
import { orgApi, unitName } from '../../api/orgs.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'

interface Draft extends BudgetLineInput {
  key: string
}

const KINDS: { kind: BudgetKind; label: () => string }[] = [
  { kind: 'income', label: () => t('Einnahmen') },
  { kind: 'expense', label: () => t('Ausgaben') },
]

function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function drafts(report: BudgetReport): Draft[] {
  return report.lines.map((l) => ({
    key: `l${l.id}`,
    kind: l.kind,
    category: l.category,
    department: l.department,
    amount: l.amount,
    note: l.note,
  }))
}

function num(value: string | null | undefined): number {
  const n = Number(String(value ?? '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}

/** Abweichung aus Sicht der Kasse: mehr Einnahmen bzw. weniger Ausgaben sind gut. */
function Deviation({ kind, plan, actual }: { kind: BudgetKind; plan: number; actual: number }) {
  const diff = actual - plan
  if (diff === 0) return <span className="muted">{euro(0)}</span>
  const good = kind === 'income' ? diff > 0 : diff < 0
  return (
    <span className={good ? 'amount-in' : 'amount-out'}>
      {diff > 0 ? '+' : ''}
      {euro(diff)}
    </span>
  )
}

function percent(plan: number, actual: number): string {
  if (plan <= 0) return ''
  return `${Math.round((100 * actual) / plan)} %`
}

export function BudgetPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const tm = useTerms()
  const [year, setYear] = useState<number | null>(null)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [lines, setLines] = useState<Draft[] | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [adopting, setAdopting] = useState(false)
  const [adoptedOn, setAdoptedOn] = useState(todayIso())
  const [adoptedBy, setAdoptedBy] = useState('')
  const categories = useLoad(() => financeApi.categories(org.id), [org.id])
  const departments = useLoad(
    () => (org.type === 'club' ? orgApi.departmentChoices(org.id) : Promise.resolve([])),
    [org.id, org.type],
  )

  const loaded = useLoad(() => financeApi.budget(org.id, year), [org.id, year])
  // Nach dem Speichern liefert der Server den neuen Stand; er gilt, bis das Jahr wechselt
  const [saved, setSaved] = useState<{ year: number | null; data: BudgetReport } | null>(null)
  const report = saved && saved.year === year ? saved.data : loaded.data

  const cats = useMemo(() => {
    const map = new Map<number, Category>()
    for (const c of categories.data ?? []) map.set(c.id, c)
    return map
  }, [categories.data])

  if (loaded.error) return <LoadError message={loaded.error} onRetry={() => void loaded.reload()} />
  if (!report || !categories.data) return <Loading />
  const r = report
  const draft = !r.budget || r.budget.status === 'draft'
  const editing = lines !== null
  const future = r.phase === 'future'
  const current = r.phase === 'current'
  const units = departments.data ?? []

  function apply(next: BudgetReport, text?: string) {
    setSaved({ year, data: next })
    setLines(null)
    setNote(next.budget?.note ?? '')
    if (text) setNotice({ kind: 'success', text })
  }

  async function run(action: () => Promise<BudgetReport>, text: string) {
    setBusy(true)
    setNotice(null)
    try {
      apply(await action(), text)
      return true
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err) })
      return false
    } finally {
      setBusy(false)
    }
  }

  async function copy(source: 'plan' | 'actual') {
    if (r.lines.length > 0) {
      const ok = await confirmDialog({
        title: t('Plan ersetzen?'),
        message: t('Die bisherigen Zeilen für {y} werden durch die Werte von {p} ersetzt.', {
          y: r.label,
          p: r.previous_label,
        }),
        confirmLabel: t('Ersetzen'),
      })
      if (!ok) return
    }
    await run(
      () => financeApi.copyBudget(org.id, r.year, source, r.budget?.version),
      source === 'plan'
        ? t('Plan von {p} übernommen.', { p: r.previous_label })
        : t('Ist von {p} übernommen.', { p: r.previous_label }),
    )
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!lines) return
    await run(
      () =>
        financeApi.saveBudget(org.id, r.year, {
          lines: lines.map((l) => ({
            kind: l.kind,
            category: l.category,
            department: l.department,
            amount: l.amount.replace(',', '.'),
            note: l.note,
          })),
          note,
          version: r.budget?.version,
        }),
      t('Haushaltsplan gespeichert.'),
    )
  }

  async function adopt(e: FormEvent) {
    e.preventDefault()
    const ok = await run(
      () =>
        financeApi.budgetStatus(org.id, r.year, {
          status: 'adopted',
          adopted_on: adoptedOn,
          adopted_by: adoptedBy,
          version: r.budget?.version,
        }),
      t('Als beschlossen eingetragen.'),
    )
    if (ok) setAdopting(false)
  }

  async function reopen() {
    const ok = await confirmDialog({
      title: t('Wieder als Entwurf bearbeiten?'),
      message: t(
        'Der Beschluss wird zurückgenommen. Nach den Änderungen bitte erneut als beschlossen eintragen.',
      ),
      confirmLabel: t('Als Entwurf bearbeiten'),
      danger: false,
    })
    if (!ok) return
    await run(
      () =>
        financeApi.budgetStatus(org.id, r.year, { status: 'draft', version: r.budget?.version }),
      t('Der Plan ist wieder ein Entwurf.'),
    )
  }

  async function remove() {
    const ok = await confirmDialog({
      title: t('Haushaltsplan {y} löschen?', { y: r.label }),
      message: t('Alle Planzeilen dieses Jahres werden gelöscht. Die Buchungen bleiben.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    await run(
      () => financeApi.deleteBudget(org.id, r.year, r.budget?.version),
      t('Haushaltsplan gelöscht.'),
    )
  }

  function startEditing() {
    setLines(drafts(r))
    setNote(r.budget?.note ?? '')
    setNotice(null)
  }

  function update(key: string, change: Partial<Draft>) {
    setLines((prev) => prev && prev.map((l) => (l.key === key ? { ...l, ...change } : l)))
  }

  function addLine(kind: BudgetKind, category?: number, department?: number | null, amount = '') {
    const first = categories.data!.find(
      (c) => c.is_active && (c.kind === 'both' || c.kind === kind),
    )
    const cat = category ?? first?.id
    if (cat === undefined) return
    setLines((prev) => [
      ...(prev ?? drafts(r)),
      {
        key: `n${Date.now()}${Math.random()}`,
        kind,
        category: cat,
        department: department ?? null,
        amount,
        note: '',
      },
    ])
  }

  const lineOf = (d: Draft): BudgetLine | undefined =>
    r.lines.find(
      (l) => l.kind === d.kind && l.category === d.category && l.department === d.department,
    )

  function totalsRow(kind: BudgetKind | 'result', label: string, totals: BudgetTotals) {
    const plan = editing && kind !== 'result' ? sumDraft(kind) : num(totals.plan)
    const planShown = editing && kind === 'result' ? sumDraft('income') - sumDraft('expense') : plan
    return (
      <tr>
        <th>{label}</th>
        <th className="num">{euro(planShown)}</th>
        {!future && <th className="num">{euro(totals.actual ?? 0)}</th>}
        {!future && (
          <th className="num">
            {kind !== 'result' && (
              <Deviation kind={kind} plan={planShown} actual={num(totals.actual)} />
            )}
          </th>
        )}
        {current && <th className="num">{euro(totals.forecast ?? 0)}</th>}
        <th className="num">{euro(totals.previous_plan)}</th>
        <th className="num">{euro(totals.previous_actual)}</th>
        {editing && <th />}
      </tr>
    )
  }

  function sumDraft(kind: BudgetKind): number {
    return (lines ?? []).filter((l) => l.kind === kind).reduce((s, l) => s + num(l.amount), 0)
  }

  function categoryLabel(id: number, department: number | null): string {
    const name = cats.get(id)?.name ?? '?'
    if (!department) return name
    const unit = units.find((u) => u.id === department)
    return unit ? `${name} · ${unitName(unit)}` : name
  }

  function section(kind: BudgetKind, label: string) {
    const shown: Draft[] = editing
      ? lines!.filter((l) => l.kind === kind)
      : drafts(r).filter((l) => l.kind === kind)
    const unplanned = r.unplanned.filter((u) => u.kind === kind)
    const choices = categories.data!.filter(
      (c) => c.kind === 'both' || c.kind === kind || shown.some((l) => l.category === c.id),
    )
    return (
      <div className="card card-wide" key={kind} data-testid={`budget-${kind}`}>
        <div className="card-head">
          <h2>{label}</h2>
          {editing && (
            <button
              type="button"
              className="button button-ghost push-right"
              onClick={() => addLine(kind)}
            >
              {t('Zeile hinzufügen')}
            </button>
          )}
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Kategorie')}</th>
                <th className="num">{t('Plan {y}', { y: r.label })}</th>
                {!future && <th className="num">{t('Ist {y}', { y: r.label })}</th>}
                {!future && <th className="num">{t('Abweichung')}</th>}
                {current && <th className="num">{t('Hochrechnung')}</th>}
                <th className="num">{t('Plan {y}', { y: r.previous_label })}</th>
                <th className="num">{t('Ist {y}', { y: r.previous_label })}</th>
                {editing && <th className="actions" />}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && unplanned.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    {t('Noch keine Zeilen.')}
                  </td>
                </tr>
              )}
              {shown.map((d) => {
                const saved = lineOf(d)
                const actual = saved && !future ? num(saved.actual) : 0
                return (
                  <tr key={d.key}>
                    <td>
                      {editing ? (
                        <div className="button-row">
                          <select
                            className="inline-edit"
                            aria-label={t('Kategorie')}
                            value={d.category}
                            onChange={(e) => update(d.key, { category: Number(e.target.value) })}
                          >
                            {choices.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                          {units.length > 0 && (
                            <select
                              className="inline-edit"
                              aria-label={tm.sg}
                              value={d.department ?? ''}
                              onChange={(e) =>
                                update(d.key, {
                                  department: e.target.value ? Number(e.target.value) : null,
                                })
                              }
                            >
                              <option value="">{t('alle')}</option>
                              {units.map((u) => (
                                <option key={u.id} value={u.id}>
                                  {unitName(u)}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      ) : (
                        <>
                          {categoryLabel(d.category, d.department)}
                          {d.note && <div className="muted small">{d.note}</div>}
                        </>
                      )}
                    </td>
                    <td className="num">
                      {editing ? (
                        <input
                          className="inline-edit num"
                          inputMode="decimal"
                          aria-label={t('Plan {y}', { y: r.label })}
                          value={d.amount}
                          onChange={(e) => update(d.key, { amount: e.target.value })}
                        />
                      ) : (
                        euro(d.amount)
                      )}
                    </td>
                    {!future && <td className="num">{saved ? euro(actual) : ''}</td>}
                    {!future && (
                      <td className="num">
                        {saved && <Deviation kind={kind} plan={num(d.amount)} actual={actual} />}
                        {saved && (
                          <div className="muted small">{percent(num(d.amount), actual)}</div>
                        )}
                      </td>
                    )}
                    {current && (
                      <td className="num">{saved?.forecast ? euro(saved.forecast) : ''}</td>
                    )}
                    <td className="num">{saved?.previous_plan ? euro(saved.previous_plan) : ''}</td>
                    <td className="num">{saved ? euro(saved.previous_actual) : ''}</td>
                    {editing && (
                      <td className="actions">
                        <button
                          type="button"
                          className="button button-ghost"
                          onClick={() =>
                            setLines((prev) => prev && prev.filter((l) => l.key !== d.key))
                          }
                        >
                          {t('Entfernen')}
                        </button>
                      </td>
                    )}
                  </tr>
                )
              })}
              {unplanned.map((u) => (
                <tr key={`u${u.category}-${u.department ?? ''}`} className="muted">
                  <td>
                    {categoryLabel(u.category, u.department)}{' '}
                    <span className="small">({t('nicht geplant')})</span>
                  </td>
                  <td className="num" />
                  {!future && <td className="num">{euro(u.actual)}</td>}
                  {!future && <td className="num" />}
                  {current && <td className="num" />}
                  <td className="num" />
                  <td className="num" />
                  {editing && (
                    <td className="actions">
                      <button
                        type="button"
                        className="button button-ghost"
                        onClick={() => addLine(kind, u.category, u.department, '')}
                      >
                        {t('In den Plan')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>{totalsRow(kind, t('Summe'), r.totals[kind])}</tfoot>
          </table>
        </div>
      </div>
    )
  }

  const pdf = financeApi.budgetFileUrl(org.id, r.year, 'pdf')
  const xlsx = financeApi.budgetFileUrl(org.id, r.year, 'xlsx')

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Haushaltsplan')}</h2>
      <div className="card card-wide filters">
        <label>
          {t('Geschäftsjahr')}{' '}
          <select
            value={r.year}
            disabled={editing}
            onChange={(e) => setYear(Number(e.target.value))}
          >
            {r.years.map((y) => (
              <option key={y.year} value={y.year}>
                {y.label}
              </option>
            ))}
          </select>
        </label>
        {r.budget && (
          <span className="button-row push-right">
            <a className="button button-ghost" href={pdf} target="_blank" rel="noreferrer">
              {t('PDF')}
            </a>
            <a className="button button-ghost" href={xlsx}>
              {t('Excel')}
            </a>
          </span>
        )}
      </div>
      <p className="muted small">
        {t(
          'Der Haushaltsplan legt fest, was der Verein im Geschäftsjahr je Kategorie einnehmen und ausgeben will. Das Ist kommt aus dem Kassenbuch, Umbuchungen zählen nicht. Eine Zeile für eine Untereinheit zählt nur deren Buchungen, eine Zeile für alle den Rest der Kategorie.',
        )}
        {current &&
          r.elapsed_percent !== null &&
          ' ' +
            t(
              'Vom Geschäftsjahr sind {p} % vorbei. Die Hochrechnung nimmt an, dass bis zum Jahresende noch so viel dazukommt wie im Vorjahr ab heute; ohne Vorjahr gilt der Plan.',
              { p: r.elapsed_percent },
            )}
      </p>
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}

      {r.budget ? (
        <div className="card card-wide" data-testid="budget-status">
          <div className="card-head">
            <h2>
              {r.budget.status === 'adopted'
                ? t('Beschlossen am {d}', { d: formatDate(r.budget.adopted_on ?? '') })
                : t('Entwurf')}
            </h2>
            {canEdit && !editing && (
              <span className="button-row push-right">
                {draft ? (
                  <>
                    <button type="button" className="button" onClick={startEditing}>
                      {t('Bearbeiten')}
                    </button>
                    <button
                      type="button"
                      className="button button-ghost"
                      disabled={busy || r.lines.length === 0}
                      onClick={() => setAdopting(true)}
                    >
                      {t('Als beschlossen eintragen')}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="button button-ghost"
                    disabled={busy}
                    onClick={() => void reopen()}
                  >
                    {t('Wieder als Entwurf bearbeiten')}
                  </button>
                )}
              </span>
            )}
          </div>
          {r.budget.status === 'adopted' && r.budget.adopted_by && (
            <p>{t('Beschlossen durch: {x}', { x: r.budget.adopted_by })}</p>
          )}
          {r.budget.status === 'adopted' && (
            <p className="muted small">
              {t('Ein beschlossener Plan ist gesperrt. Zum Ändern wieder als Entwurf bearbeiten.')}
            </p>
          )}
          {r.budget.note && !editing && <p className="pre-line">{r.budget.note}</p>}
          {adopting && (
            <form className="grid-3" onSubmit={adopt}>
              <Field
                label={t('beschlossen am')}
                type="date"
                required
                max={todayIso()}
                value={adoptedOn}
                onChange={(e) => setAdoptedOn(e.target.value)}
              />
              <Field
                label={t('beschlossen durch (optional)')}
                placeholder={t('z. B. Mitgliederversammlung')}
                value={adoptedBy}
                onChange={(e) => setAdoptedBy(e.target.value)}
              />
              <div className="button-row">
                <button type="submit" className="button" disabled={busy}>
                  {t('Eintragen')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setAdopting(false)}
                >
                  {t('Abbrechen')}
                </button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <div className="card card-wide" data-testid="budget-empty">
          <h2>{t('Noch kein Haushaltsplan für {y}', { y: r.label })}</h2>
          {canEdit ? (
            <>
              <p>{t('Am schnellsten geht es mit den Zahlen des Vorjahres als Vorlage.')}</p>
              <div className="button-row">
                {r.previous_has_budget && (
                  <button
                    type="button"
                    className="button"
                    disabled={busy}
                    onClick={() => void copy('plan')}
                  >
                    {t('Plan von {p} übernehmen', { p: r.previous_label })}
                  </button>
                )}
                <button
                  type="button"
                  className={r.previous_has_budget ? 'button button-ghost' : 'button'}
                  disabled={busy}
                  onClick={() => void copy('actual')}
                >
                  {t('Ist von {p} übernehmen', { p: r.previous_label })}
                </button>
                <button type="button" className="button button-ghost" onClick={startEditing}>
                  {t('Leer beginnen')}
                </button>
              </div>
            </>
          ) : (
            <p className="muted">{t('Die Kasse hat für dieses Jahr noch nichts geplant.')}</p>
          )}
        </div>
      )}

      {(r.budget || editing) && (
        <form onSubmit={save} className="stack">
          {editing && draft && r.budget && (
            <div className="button-row">
              {r.previous_has_budget && (
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void copy('plan')}
                >
                  {t('Plan von {p} übernehmen', { p: r.previous_label })}
                </button>
              )}
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() => void copy('actual')}
              >
                {t('Ist von {p} übernehmen', { p: r.previous_label })}
              </button>
            </div>
          )}
          {KINDS.map((k) => section(k.kind, k.label()))}
          <div className="card card-wide" data-testid="budget-result">
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Ergebnis')}</th>
                    <th className="num">{t('Plan {y}', { y: r.label })}</th>
                    {!future && <th className="num">{t('Ist {y}', { y: r.label })}</th>}
                    {!future && <th className="num" />}
                    {current && <th className="num">{t('Hochrechnung')}</th>}
                    <th className="num">{t('Plan {y}', { y: r.previous_label })}</th>
                    <th className="num">{t('Ist {y}', { y: r.previous_label })}</th>
                    {editing && <th />}
                  </tr>
                </thead>
                <tfoot>{totalsRow('result', t('Einnahmen minus Ausgaben'), r.totals.result)}</tfoot>
              </table>
            </div>
          </div>
          {editing && (
            <>
              <label className="field">
                <span>{t('Bemerkung (optional)')}</span>
                <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="button-row">
                <button type="submit" className="button" disabled={busy}>
                  {t('Speichern')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => {
                    setLines(null)
                    setNote(r.budget?.note ?? '')
                  }}
                >
                  {t('Abbrechen')}
                </button>
                {r.budget && (
                  <button
                    type="button"
                    className="button button-danger push-right"
                    disabled={busy}
                    onClick={() => void remove()}
                  >
                    {t('Plan löschen')}
                  </button>
                )}
              </div>
            </>
          )}
        </form>
      )}
    </div>
  )
}
