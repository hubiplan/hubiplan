// Gemeinsame Bausteine der Auslagen (docs/auslagen.md): Formular für Mitglied, Kasse und
// persönlichen Link, Anzeige von Positionen, Belegen und Verlauf.
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type {
  ClaimInput,
  Choice,
  ExpenseClaim,
  ExpenseKind,
  ExpenseStatus,
  InvoiceTo,
  Payout,
} from '../../api/expenses.ts'
import { formatDate, formatDateTime } from '../../components/forms.ts'
import { amountText, euro, kindLabel } from './format.ts'
import { Segmented } from '../../components/PageHeader.tsx'
import { Alert, Field, SelectField } from '../../components/ui.tsx'
import { formatEuro } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'
import './expenses.css'
import { HowTo, Term, Why } from '../../learning/Aids.tsx'

const STATUS_BADGE: Record<ExpenseStatus, string> = {
  draft: 'badge',
  submitted: 'badge badge-open',
  question: 'badge badge-warn',
  confirmed: 'badge badge-info',
  approved: 'badge badge-info',
  paid: 'badge badge-ok',
  rejected: 'badge badge-error',
  withdrawn: 'badge',
  waived: 'badge badge-ok',
}

export function StatusBadge({ claim }: { claim: ExpenseClaim }) {
  return <span className={STATUS_BADGE[claim.status]}>{claim.status_label}</span>
}

/** Positionen, Fahrt, Bankverbindung und gekürzter Betrag */
export function ClaimFacts({ claim }: { claim: ExpenseClaim }) {
  return (
    <dl className="expense-facts">
      <dt>{t('Art')}</dt>
      <dd>{kindLabel(claim.kind)}</dd>
      {claim.purchase_date && (
        <>
          <dt>{claim.kind === 'mileage' ? t('Fahrt am') : t('Gekauft am')}</dt>
          <dd>{formatDate(claim.purchase_date)}</dd>
        </>
      )}
      {claim.kind === 'mileage' && (
        <>
          <dt>{t('Strecke')}</dt>
          <dd>{claim.route || '—'}</dd>
          <dt>{t('Kilometer')}</dt>
          <dd>{t('{km} km × {rate}', { km: claim.km ?? '—', rate: euro(claim.km_rate) })}</dd>
        </>
      )}
      {claim.department_name && (
        <>
          <dt>{t('Untereinheit')}</dt>
          <dd>{claim.department_name}</dd>
        </>
      )}
      {claim.project_name && (
        <>
          <dt>{t('Projekt')}</dt>
          <dd>{claim.project_name}</dd>
        </>
      )}
      {claim.kind !== 'mileage' &&
        claim.lines.map((line) => (
          <div key={line.id ?? line.text} className="contents">
            <dt>{line.text || t('Betrag')}</dt>
            <dd>
              {euro(line.amount)}
              {line.category_name && <span className="muted small"> · {line.category_name}</span>}
            </dd>
          </div>
        ))}
      <dt>{t('Summe')}</dt>
      <dd>
        <strong>{euro(claim.total)}</strong>
      </dd>
      {claim.approved_amount !== null && claim.approved_amount !== claim.total && (
        <>
          <dt>{t('Freigegeben')}</dt>
          <dd>
            {euro(claim.approved_amount)}
            {claim.reduce_reason && <span className="muted small"> · {claim.reduce_reason}</span>}
          </dd>
        </>
      )}
      {claim.advance_number && (
        <>
          <dt>
            <Term k="advance">{t('Abrechnung des Vorschusses')}</Term>
          </dt>
          <dd>{claim.advance_number}</dd>
        </>
      )}
      {claim.amount_due !== claim.total && (
        <>
          <dt>{t('Auszuzahlen')}</dt>
          <dd>{euro(claim.amount_due)}</dd>
        </>
      )}
      <dt>{t('Auszahlung')}</dt>
      <dd>
        {claim.payout === 'cash'
          ? t('bar')
          : claim.payout === 'waiver'
            ? t('Verzicht (Spende)')
            : claim.payee
              ? `${claim.payee.holder} · ${claim.payee.iban}`
              : t('Überweisung')}
      </dd>
      {claim.reject_reason && (
        <>
          <dt>{t('Grund der Ablehnung')}</dt>
          <dd>{claim.reject_reason}</dd>
        </>
      )}
      {claim.booking_number && (
        <>
          <dt>{t('Buchung')}</dt>
          <dd>{claim.booking_number}</dd>
        </>
      )}
    </dl>
  )
}

/** Belege mit Link zum Ansehen */
export function ClaimFiles({
  claim,
  url,
  onRemove,
}: {
  claim: ExpenseClaim
  url: (fileId: number) => string
  onRemove?: (fileId: number) => void
}) {
  if (!claim.files?.length) return <p className="muted">{t('Noch kein Beleg.')}</p>
  return (
    <ul className="expense-items">
      {claim.files.map((f) => (
        <li key={f.id}>
          <a href={url(f.id)} target="_blank" rel="noreferrer">
            {f.name}
          </a>
          {f.einvoice?.payable && (
            <span className="muted small">
              {' '}
              · {t('E-Rechnung über {amount}', { amount: euro(f.einvoice.payable) })}
            </span>
          )}
          {onRemove && (
            <button
              type="button"
              className="button button-ghost"
              onClick={() => onRemove(f.id)}
              aria-label={t('Beleg {name} entfernen', { name: f.name })}
            >
              {t('Entfernen')}
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}

export function ClaimEvents({ claim }: { claim: ExpenseClaim }) {
  if (!claim.events?.length) return null
  return (
    <details>
      <summary>{t('Verlauf')}</summary>
      <ul className="expense-items">
        {claim.events.map((e, i) => (
          <li key={i}>
            <span className="muted small">{formatDateTime(e.at)}</span> · {e.label}
            {e.who && <> · {e.who}</>}
            {e.text && <div>{e.text}</div>}
          </li>
        ))}
      </ul>
    </details>
  )
}

export interface FormChoices {
  mileage_enabled: boolean
  km_rate: string
  advances_enabled?: boolean
  departments?: Choice[]
  projects?: Choice[]
  categories?: Choice[]
  open_advances?: { id: number; number: string; amount: string; purpose: string }[]
  payee?: { holder: string; iban: string } | null
}

interface LineRow {
  amount: string
  text: string
  category: string
}

function startLines(claim?: ExpenseClaim | null): LineRow[] {
  if (claim?.lines.length && claim.kind !== 'mileage')
    return claim.lines.map((l) => ({
      amount: l.amount.replace('.', ','),
      text: l.text,
      category: l.category ? String(l.category) : '',
    }))
  return [{ amount: '', text: '', category: '' }]
}

const today = () => new Date().toISOString().slice(0, 10)

/**
 * Formular einer Auslage. ``onSubmit`` bekommt die Angaben, die neuen Belege und ob gleich
 * eingereicht werden soll; Fehler zeigt der Aufrufer über ``errors``.
 */
export function ClaimForm({
  claim,
  choices,
  errors = {},
  busy,
  withFiles = true,
  treasury = false,
  allowDraft = true,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  claim?: ExpenseClaim | null
  choices: FormChoices
  errors?: Record<string, string>
  busy: boolean
  withFiles?: boolean
  treasury?: boolean
  allowDraft?: boolean
  submitLabel?: string
  onSubmit: (data: ClaimInput, files: File[], submit: boolean) => void
  onCancel?: () => void
}) {
  const [kind, setKind] = useState<ExpenseKind>(claim?.kind ?? 'expense')
  const [purpose, setPurpose] = useState(claim?.purpose ?? '')
  const [note, setNote] = useState(claim?.note ?? '')
  const [day, setDay] = useState(claim?.purchase_date ?? today())
  const [lines, setLines] = useState<LineRow[]>(() => startLines(claim))
  const [route, setRoute] = useState(claim?.route ?? '')
  const [km, setKm] = useState(claim?.km?.replace('.', ',') ?? '')
  const [invoiceTo, setInvoiceTo] = useState<InvoiceTo>(claim?.invoice_to ?? 'club')
  const [payout, setPayout] = useState<Payout>(claim?.payout === 'cash' ? 'cash' : 'bank')
  const [holder, setHolder] = useState(claim?.payee?.holder ?? choices.payee?.holder ?? '')
  const [iban, setIban] = useState(claim?.payee?.iban ?? choices.payee?.iban ?? '')
  const [department, setDepartment] = useState(claim?.department ? String(claim.department) : '')
  const [project, setProject] = useState(claim?.project ? String(claim.project) : '')
  const [advance, setAdvance] = useState(claim?.advance ? String(claim.advance) : '')
  const [files, setFiles] = useState<File[]>([])
  const camera = useRef<HTMLInputElement>(null)
  const kinds: { value: ExpenseKind; label: string }[] = [
    { value: 'expense', label: t('Auslage mit Beleg') },
    ...(choices.mileage_enabled ? [{ value: 'mileage' as const, label: t('Fahrtkosten') }] : []),
    ...(choices.advances_enabled ? [{ value: 'advance' as const, label: t('Vorschuss') }] : []),
  ]
  const kmTotal = Number(amountText(km) || 0) * Number(choices.km_rate || 0)
  const sum = lines.reduce((s, l) => s + (Number(amountText(l.amount)) || 0), 0)
  const addFiles = (list: FileList | null) => {
    if (list?.length) setFiles((old) => [...old, ...Array.from(list)].slice(0, 10))
  }
  const send = (e: FormEvent, submit: boolean) => {
    e.preventDefault()
    const data: ClaimInput = {
      kind,
      purpose,
      purchase_date: kind === 'advance' ? null : day,
      payout,
      payee: payout === 'bank' ? { holder, iban: iban.replace(/\s/g, '').toUpperCase() } : null,
    }
    if (kind === 'mileage') {
      data.route = route
      data.km = amountText(km) || null
    } else {
      data.lines = lines
        .filter((l) => l.amount.trim())
        .map((l) => ({
          amount: amountText(l.amount),
          text: l.text,
          ...(treasury && l.category ? { category: Number(l.category) } : {}),
        }))
    }
    if (kind === 'expense') data.invoice_to = invoiceTo
    if (choices.departments?.length) data.department = department ? Number(department) : null
    if (choices.projects?.length) data.project = project ? Number(project) : null
    if (kind === 'expense' && choices.open_advances?.length)
      data.advance = advance ? Number(advance) : null
    if (treasury) data.note = note
    onSubmit(data, files, submit)
  }
  const fieldError = (key: string) => errors[key]
  return (
    <form className="stack" onSubmit={(e) => send(e, true)} noValidate>
      {kinds.length > 1 && (
        <Segmented label={t('Art der Auslage')} options={kinds} value={kind} onChange={setKind} />
      )}
      <label className="field">
        <span>{t('Wofür, für wen?')}</span>
        <textarea
          value={purpose}
          maxLength={1000}
          rows={2}
          required
          aria-invalid={!!fieldError('purpose')}
          placeholder={t('z. B. Uniformhemden für die Jugend, Sommerlager')}
          onChange={(e) => setPurpose(e.target.value)}
        />
        {fieldError('purpose') && <small className="field-error">{fieldError('purpose')}</small>}
      </label>
      {kind !== 'advance' && (
        <Field
          label={kind === 'mileage' ? t('Datum der Fahrt') : t('Datum des Kaufs')}
          type="date"
          value={day ?? ''}
          max={today()}
          error={fieldError('purchase_date')}
          onChange={(e) => setDay(e.target.value)}
        />
      )}
      {kind === 'mileage' ? (
        <>
          <Field
            label={t('Start, Ziel und Anlass')}
            value={route}
            maxLength={300}
            error={fieldError('route')}
            onChange={(e) => setRoute(e.target.value)}
          />
          <Field
            label={t('Gefahrene Kilometer (hin und zurück)')}
            inputMode="decimal"
            value={km}
            error={fieldError('km')}
            hint={t('{rate} je km, zusammen {sum}', {
              rate: euro(choices.km_rate),
              sum: formatEuro(kmTotal),
            })}
            onChange={(e) => setKm(e.target.value)}
          />
          <HowTo k="calc_mileage" />
        </>
      ) : (
        <fieldset className="stack">
          <legend>{kind === 'advance' ? t('Benötigter Betrag') : t('Beträge')}</legend>
          {lines.map((line, i) => (
            <div key={i} className="expense-line">
              <Field
                label={t('Betrag in €')}
                inputMode="decimal"
                value={line.amount}
                onChange={(e) =>
                  setLines(lines.map((l, j) => (j === i ? { ...l, amount: e.target.value } : l)))
                }
              />
              <Field
                label={t('Was (optional)')}
                value={line.text}
                maxLength={200}
                onChange={(e) =>
                  setLines(lines.map((l, j) => (j === i ? { ...l, text: e.target.value } : l)))
                }
              />
              {treasury && !!choices.categories?.length && (
                <SelectField
                  label={t('Kategorie')}
                  value={line.category}
                  onChange={(e) =>
                    setLines(
                      lines.map((l, j) => (j === i ? { ...l, category: e.target.value } : l)),
                    )
                  }
                >
                  <option value="">{t('später wählen')}</option>
                  {choices.categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </SelectField>
              )}
              {lines.length > 1 && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setLines(lines.filter((_, j) => j !== i))}
                >
                  {t('Position entfernen')}
                </button>
              )}
            </div>
          ))}
          {fieldError('lines') && <small className="field-error">{fieldError('lines')}</small>}
          <div className="button-row">
            {kind === 'expense' && lines.length < 20 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setLines([...lines, { amount: '', text: '', category: '' }])}
              >
                {t('Weitere Position')}
              </button>
            )}
            {lines.length > 1 && (
              <span className="muted">{t('Zusammen {sum}', { sum: formatEuro(sum) })}</span>
            )}
          </div>
        </fieldset>
      )}
      {kind === 'expense' && (
        <SelectField
          label={t('Auf wen lautet die Rechnung?')}
          value={invoiceTo}
          hint={t('Auf den Verein ausgestellte Rechnungen erlauben den Vorsteuerabzug.')}
          onChange={(e) => setInvoiceTo(e.target.value as InvoiceTo)}
        >
          <option value="club">{t('den Verein')}</option>
          <option value="member">{t('mich')}</option>
          <option value="none">{t('ohne Namen (Kassenbon)')}</option>
        </SelectField>
      )}
      {kind === 'expense' && <Why k="expense_invoice_to" />}
      {kind === 'expense' && !!choices.open_advances?.length && (
        <SelectField
          label={t('Rechnet einen Vorschuss ab')}
          value={advance}
          onChange={(e) => setAdvance(e.target.value)}
        >
          <option value="">{t('nein')}</option>
          {choices.open_advances.map((a) => (
            <option key={a.id} value={a.id}>
              {`${a.number} · ${euro(a.amount)} · ${a.purpose}`}
            </option>
          ))}
        </SelectField>
      )}
      {!!choices.departments?.length && (
        <SelectField
          label={t('Für welche Untereinheit? (optional)')}
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
        >
          <option value="">{t('den ganzen Verein')}</option>
          {choices.departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </SelectField>
      )}
      {!!choices.projects?.length && (
        <SelectField
          label={t('Projekt oder Veranstaltung (optional)')}
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">{t('keins')}</option>
          {choices.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
      )}
      <fieldset className="stack">
        <legend>{t('Auszahlung')}</legend>
        <Segmented
          label={t('Auszahlung')}
          options={[
            { value: 'bank', label: t('Überweisung') },
            { value: 'cash', label: t('bar') },
          ]}
          value={payout === 'cash' ? 'cash' : 'bank'}
          onChange={(v) => setPayout(v as Payout)}
        />
        {payout === 'bank' && (
          <>
            <Field
              label={t('Kontoinhaber')}
              value={holder}
              maxLength={70}
              autoComplete="name"
              onChange={(e) => setHolder(e.target.value)}
            />
            <Field
              label={t('IBAN')}
              value={iban}
              maxLength={42}
              autoComplete="off"
              spellCheck={false}
              error={fieldError('payee')}
              onChange={(e) => setIban(e.target.value)}
            />
          </>
        )}
      </fieldset>
      {treasury && (
        <label className="field">
          <span>{t('Ohne Beleg: Begründung (Eigenbeleg)')}</span>
          <textarea
            value={note}
            maxLength={300}
            rows={2}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
      )}
      {treasury && <Why k="expense_no_receipt" />}
      {withFiles && kind === 'expense' && (
        <fieldset className="stack">
          <legend>{t('Belege')}</legend>
          <p className="muted small">
            {t(
              'Foto oder Datei (Bild, PDF oder E-Rechnung), bis zu 10 Belege, je höchstens 15 MB.',
            )}
          </p>
          <div className="button-row">
            <button type="button" className="button" onClick={() => camera.current?.click()}>
              {t('Foto aufnehmen')}
            </button>
            <label className="button button-ghost file-button">
              {t('Datei wählen')}
              <input
                type="file"
                className="file-input"
                multiple
                accept="image/*,application/pdf,.pdf,.xml,application/xml"
                onChange={(e) => {
                  addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </label>
            <input
              ref={camera}
              type="file"
              className="file-input"
              accept="image/*"
              capture="environment"
              hidden
              aria-label={t('Foto aufnehmen')}
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>
          {files.length > 0 && (
            <ul className="expense-items">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`}>
                  {f.name}{' '}
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setFiles(files.filter((_, j) => j !== i))}
                  >
                    {t('Entfernen')}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {fieldError('files') && <small className="field-error">{fieldError('files')}</small>}
          {fieldError('file') && <small className="field-error">{fieldError('file')}</small>}
        </fieldset>
      )}
      {errors.detail && <Alert kind="error">{errors.detail}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel ?? t('Einreichen')}
        </button>
        {allowDraft && (
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={(e) => send(e as unknown as FormEvent, false)}
          >
            {t('Als Entwurf speichern')}
          </button>
        )}
        {onCancel && (
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}
