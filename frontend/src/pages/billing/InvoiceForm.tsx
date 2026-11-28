import { todayIso } from '../../api/members.ts'
import { useCallback, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { billingApi } from '../../api/billing.ts'
import { ApiError } from '../../api/client.ts'
import type { BillingSettings, Invoice } from '../../api/billing.ts'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type { PickedMember } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { errorMessage, useAutoSave, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useRevealFocus } from '../../components/revealFocus.ts'
import { hasMembersModule } from './invoicesHelpers.ts'

interface LineDraft {
  id?: number
  text: string
  detail: string
  amount: string
  vat_rate: string
}

export function InvoiceForm({
  settings,
  invoice,
  onCancel,
  onSaved,
}: {
  settings: BillingSettings
  invoice: Invoice | null
  onCancel: () => void
  onSaved: (inv: Invoice) => void
}) {
  const org = useActiveOrg()
  const federation = settings.org_type === 'federation'
  // Arbeitsbereich einer Untereinheit: Rechnungen nur an ihre Mitglieder
  const unit = settings.org_type === 'unit'
  const searchUnitMembers = useCallback(
    (term: string) => billingApi.members(org.id, term),
    [org.id],
  )
  // Für alle Einheiten gleich: an ein Mitglied (wenn sie eigene führt) oder an eine Untereinheit
  const canMember = (settings.keeps_members ?? !federation) && (unit || hasMembersModule(org))
  const subUnits = unit ? [] : (settings.units ?? (federation ? settings.clubs : []))
  const initialUnit = invoice?.club ?? invoice?.department ?? null
  const [kind, setKind] = useState<'member' | 'unit'>(() => {
    if (invoice) return invoice.recipient_kind === 'member' ? 'member' : 'unit'
    return canMember ? 'member' : 'unit'
  })
  const [member, setMember] = useState<PickedMember | null>(null)
  const [unitId, setUnitId] = useState(initialUnit ? String(initialUnit) : '')
  const [subject, setSubject] = useState(invoice?.subject ?? 'Rechnung')
  const [date, setDate] = useState(() => invoice?.date ?? todayIso())
  const [note, setNote] = useState(invoice?.note ?? '')
  const [project, setProject] = useState(invoice?.project ? String(invoice.project) : '')
  const withProjects = org.modules.includes('finance') && org.permissions.includes(PERM.financeView)
  const projects = useLoad(
    () => (withProjects ? financeApi.projects(org.id) : Promise.resolve([])),
    [org.id, withProjects],
  )
  const usableProjects = (projects.data ?? []).filter(
    (p) => p.status !== 'done' || String(p.id) === project,
  )
  const [lines, setLines] = useState<LineDraft[]>(
    invoice?.lines.map((l) => ({
      id: l.id,
      text: l.text,
      detail: l.detail,
      amount: l.amount.replace('.', ','),
      vat_rate: l.vat_rate ?? '',
    })) ?? [{ text: '', detail: '', amount: '', vat_rate: '' }],
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const keepMember = invoice?.recipient_kind === 'member' && !member

  function setLine(i: number, patch: Partial<LineDraft>) {
    setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)))
  }

  // Ganz leere Zusatzzeilen zählen nicht; jede angefangene Zeile muss vollständig sein.
  // Summe und gespeicherte Posten kommen aus derselben Liste.
  const filled = lines
    .map((l, i) => ({ ...l, index: i }))
    .filter((l) => l.text.trim() || l.detail.trim() || l.amount.trim())
  const lineErrors: Record<number, { text?: string; amount?: string }> = {}
  for (const l of filled) {
    const n = l.index + 1
    if (!l.text.trim())
      lineErrors[l.index] = {
        text: t('Posten {n}: Bitte eine Bezeichnung ergänzen oder den gesamten Posten entfernen.', {
          n,
        }),
      }
    const amount = parseAmount(l.amount)
    if (!amount)
      lineErrors[l.index] = {
        ...lineErrors[l.index],
        amount: t('Bitte einen Betrag eintragen (0 für einen Posten ohne Betrag).'),
      }
    else if (Number.isNaN(Number(amount)))
      lineErrors[l.index] = {
        ...lineErrors[l.index],
        amount: t('Bitte einen gültigen Betrag eintragen.'),
      }
  }
  const [showLineErrors, setShowLineErrors] = useState(false)
  const incompleteText =
    filled.length === 0
      ? t('Bitte mindestens einen Posten eintragen.')
      : Object.keys(lineErrors).length > 0
        ? t('Bitte die markierten Posten vervollständigen oder entfernen.')
        : null

  const data = {
    recipient_kind: kind,
    membership:
      kind === 'member' ? (member?.id ?? (keepMember ? invoice?.membership : null)) : null,
    unit: kind === 'unit' ? Number(unitId) || null : null,
    subject,
    date,
    note,
    ...(withProjects ? { project: Number(project) || null } : {}),
    lines: filled.map((l) => ({
      id: l.id ?? null,
      text: l.text,
      detail: l.detail,
      amount: parseAmount(l.amount),
      vat_rate: settings.vat_enabled && l.vat_rate ? l.vat_rate : null,
    })),
  }
  // Gleicher Inhalt, gleiches Objekt: sonst liefe das Autospeichern bei jedem Neuzeichnen an
  const dataJson = JSON.stringify(data)
  const draft = useMemo(() => JSON.parse(dataJson) as typeof data, [dataJson])
  const [, setFieldErrors] = useState<Record<string, string>>({})
  const lastSaved = useRef<Invoice | null>(null)

  // Bestehende Entwürfe speichern automatisch, neue erst mit „Entwurf anlegen“
  const auto = useAutoSave(
    { values: draft, setErrors: setFieldErrors },
    async (_changes, values) => {
      if (incompleteText) {
        setShowLineErrors(true)
        throw new ApiError(400, { detail: incompleteText })
      }
      const sent = filled.map((l) => lines[l.index])
      const saved = await billingApi.updateInvoice(org.id, invoice!.id, values)
      lastSaved.current = saved
      // Neue Posten bekommen ihre ID, damit das nächste Speichern sie nicht neu anlegt
      setLines((ls) =>
        ls.map((l) => {
          const k = sent.indexOf(l)
          const id = k >= 0 ? saved.lines[k]?.id : undefined
          return id && !l.id ? { ...l, id } : l
        }),
      )
      return saved
    },
    { enabled: invoice !== null, version: invoice?.version },
  )

  async function save(e: FormEvent) {
    e.preventDefault()
    if (invoice) {
      if (await auto.flush()) onSaved(lastSaved.current ?? invoice)
      return
    }
    if (incompleteText) {
      setShowLineErrors(true)
      setError(incompleteText)
      return
    }
    setBusy(true)
    setError(null)
    try {
      onSaved(await billingApi.createInvoice(org.id, data))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const total = filled.reduce((sum, l) => sum + (Number(parseAmount(l.amount)) || 0), 0)
  // VW-43: neu eingeblendetes Formular bekommt den Fokus und rückt ins Bild
  const formRef = useRevealFocus<HTMLFormElement>(!invoice, invoice ? undefined : onCancel)
  const incomplete = Object.keys(lineErrors).length > 0

  return (
    <form className="card card-wide" onSubmit={save} ref={formRef}>
      <h2>{invoice ? t('Entwurf bearbeiten') : t('Neue Rechnung')}</h2>
      {invoice && <SaveStatus auto={auto} />}
      <p className="muted small">
        {t(
          'Für Aufnahmegebühren, Umlagen, Vereinskleidung und andere Einzelposten. Eine Ermäßigung trägst du als Posten mit Minusbetrag ein.',
        )}
      </p>
      <div className="grid-3">
        {canMember && subUnits.length > 0 && (
          <SelectField
            label={t('Empfänger')}
            value={kind}
            onChange={(e) => setKind(e.target.value as 'member' | 'unit')}
          >
            <option value="member">{t('Mitglied')}</option>
            <option value="unit">{settings.department_label}</option>
          </SelectField>
        )}
        {kind === 'member' ? (
          <div>
            <MemberPicker
              orgId={org.id}
              value={member}
              onChange={setMember}
              label={t('Mitglied')}
              search={unit ? searchUnitMembers : undefined}
            />
            {keepMember && (
              <small className="muted">
                {t('bisher:')} {invoice?.recipient_name.split('\n')[0]}
              </small>
            )}
          </div>
        ) : (
          <SelectField
            label={settings.department_label}
            value={unitId}
            onChange={(e) => setUnitId(e.target.value)}
          >
            <option value="">{t('bitte wählen')}</option>
            {subUnits.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
        )}
        <Field
          label={t('Rechnungsdatum')}
          type="date"
          required
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <Field
        label={t('Betreff')}
        required
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
      />
      {projects.error && (
        <LoadError
          message={t(
            'Die Veranstaltungen konnten nicht geladen werden; deine Eingaben bleiben erhalten. {error}',
            { error: projects.error },
          )}
          onRetry={() => void projects.reload()}
        />
      )}
      {usableProjects.length > 0 && (
        <SelectField
          label={t('Veranstaltung (optional)')}
          value={project}
          hint={t('Zahlungen werden in der Kasse dieser Veranstaltung zugeordnet')}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">{t('keine')}</option>
          {usableProjects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </SelectField>
      )}
      <h3>{t('Posten')}</h3>
      {lines.map((l, i) => (
        <div key={i} className={settings.vat_enabled ? 'line-row line-row-vat' : 'line-row'}>
          <Field
            label={t('Posten {x}', { x: i + 1 })}
            value={l.text}
            error={showLineErrors ? lineErrors[i]?.text : undefined}
            onChange={(e) => setLine(i, { text: e.target.value })}
          />
          <Field
            label={t('Zusatz (optional)')}
            value={l.detail}
            onChange={(e) => setLine(i, { detail: e.target.value })}
          />
          <Field
            label={t('Betrag (€)')}
            inputMode="decimal"
            value={l.amount}
            error={showLineErrors ? lineErrors[i]?.amount : undefined}
            onChange={(e) => setLine(i, { amount: e.target.value })}
          />
          {settings.vat_enabled && (
            <SelectField
              label={t('Umsatzsteuer')}
              value={l.vat_rate ? String(Number(l.vat_rate)) : ''}
              onChange={(e) => setLine(i, { vat_rate: e.target.value })}
            >
              <option value="">{t('keine')}</option>
              {[...new Set([Number(settings.vat_rate), 19, 7])].map((r) => (
                <option key={r} value={String(r)}>
                  {r.toLocaleString(locale())} {t('% enthalten')}
                </option>
              ))}
            </SelectField>
          )}
          <button
            type="button"
            className="link-button"
            disabled={lines.length === 1}
            onClick={() => setLines((ls) => ls.filter((_, n) => n !== i))}
          >
            {t('Entfernen')}
          </button>
        </div>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            setLines((ls) => [...ls, { text: '', detail: '', amount: '', vat_rate: '' }])
          }
        >
          {t('Posten hinzufügen')}
        </button>
        <strong className="push-right">
          {t('Summe')} {euro(total)}
          {incomplete && <span className="muted small"> {t('(unvollständige Posten offen)')}</span>}
        </strong>
      </div>
      <label className="field">
        <span>{t('Hinweis auf der Rechnung (optional)')}</span>
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button
          type="submit"
          className={invoice ? 'button button-ghost' : 'button button-primary'}
          disabled={busy}
        >
          {invoice ? t('Schließen') : t('Entwurf anlegen')}
        </button>
        {!invoice && (
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}
