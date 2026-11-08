import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { billingApi } from '../../api/billing.ts'
import { newRequestKey } from '../../api/client.ts'
import { einvoiceApi } from '../../api/einvoices.ts'
import type {
  CommercialInput,
  CommercialInvoice,
  CommercialLine,
  ValidationReport,
} from '../../api/einvoices.ts'
import { euro, financeApi } from '../../api/finance.ts'
import { todayIso } from '../../api/members.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { emptyParty, PartyFields } from './PartnersPage.tsx'
import { InvoiceDocumentsPanel } from './InvoiceDocumentsPanel.tsx'

const blankLine = (): CommercialLine => ({
  text: '',
  quantity: '1',
  unit: 'C62',
  unit_price: '0',
  allowance: '0',
  charge: '0',
  adjustment_reason: '',
  tax_category: 'S',
  tax_rate: '19',
  tax_reason: '',
})

export function ValidationResult({ report }: { report: ValidationReport }) {
  if (!report.status) return null
  return (
    <div className="stack">
      <Alert kind={report.status === 'valid' ? 'success' : 'error'}>
        {report.status === 'valid'
          ? t('Technische Prüfung erfolgreich. Die fachliche Prüfung bleibt erforderlich.')
          : report.status === 'unavailable'
            ? t('Prüfung derzeit nicht verfügbar.')
            : t('Die E-Rechnung enthält Fehler.')}
      </Alert>
      <p className="muted small">{report.validator}</p>
      {(report.messages?.length ?? 0) > 0 && (
        <ul>
          {report.messages.map((message, index) => (
            <li key={index}>
              {message.code && <strong>{message.code}: </strong>}
              {message.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function EInvoicesPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const selected = params.get('rechnung')
  const [page, setPage] = useState(1)
  const list = useLoad(() => einvoiceApi.invoices(org.id, page), [org.id, page])
  const change = (id?: number | 'neu') => setParams(id ? { rechnung: String(id) } : {})
  if (selected === 'neu' && canEdit)
    return (
      <CommercialForm
        onSaved={(id) => {
          change(id)
          void list.reload()
        }}
        onClose={() => change()}
      />
    )
  if (selected && /^\d+$/.test(selected))
    return (
      <CommercialDetail
        key={`${org.id}-${selected}`}
        id={Number(selected)}
        canEdit={canEdit}
        onClose={() => {
          change()
          void list.reload()
        }}
      />
    )
  return (
    <div className="stack">
      <p>
        {t(
          'Leistungsrechnungen an Kunden mit strukturierten Rechnungsdaten und XRechnung-Ausgabe.',
        )}
      </p>
      {list.error && <Alert kind="error">{list.error}</Alert>}
      {canEdit && (
        <button className="button button-primary" onClick={() => change('neu')}>
          {t('Leistungsrechnung anlegen')}
        </button>
      )}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('Rechnung')}</th>
              <th>{t('Empfänger')}</th>
              <th>{t('Betrag')}</th>
              <th>{t('Status')}</th>
            </tr>
          </thead>
          <tbody>
            {list.data?.results.map((row) => (
              <tr key={row.id}>
                <td>
                  <button className="button button-ghost" onClick={() => change(row.id)}>
                    {row.number}
                  </button>
                </td>
                <td>{row.recipient_name}</td>
                <td>{euro(row.total)}</td>
                <td>{row.status_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data?.count === 0 && <p>{t('Noch keine Leistungsrechnungen vorhanden.')}</p>}
      </div>
      <div className="actions">
        <button
          className="button button-ghost"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          {t('Zurück')}
        </button>
        <span>{page}</span>
        <button
          className="button button-ghost"
          disabled={!list.data?.next}
          onClick={() => setPage(page + 1)}
        >
          {t('Weiter')}
        </button>
      </div>
    </div>
  )
}

function CommercialDetail({
  id,
  canEdit,
  onClose,
}: {
  id: number
  canEdit: boolean
  onClose: () => void
}) {
  const org = useActiveOrg()
  const load = useLoad(() => einvoiceApi.invoice(org.id, id), [org.id, id])
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [report, setReport] = useState<ValidationReport | null>(null)
  async function act(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
      await load.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  const invoice = load.data
  if (!invoice) return <p>{t('Lädt …')}</p>
  if (editing)
    return (
      <CommercialForm
        invoice={invoice}
        onSaved={() => {
          setEditing(false)
          void load.reload()
        }}
        onClose={() => setEditing(false)}
      />
    )
  return (
    <div className="card stack">
      <div className="page-head">
        <h2>
          {invoice.number} · {invoice.recipient_name}
        </h2>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      <p>
        {invoice.subject} · {euro(invoice.total)} · {invoice.status_label}
      </p>
      {Number(invoice.prepaid ?? 0) > 0 && (
        <p>
          {t('Angerechnete Anzahlungen')}: {euro(invoice.prepaid!)} · {t('Noch offen')}:{' '}
          {euro(invoice.outstanding)}
        </p>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {report && <ValidationResult report={report} />}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('Position')}</th>
              <th>{t('Menge')}</th>
              <th>{t('Nettopreis')}</th>
              <th>{t('Steuerkategorie')}</th>
            </tr>
          </thead>
          <tbody>
            {invoice.lines.map(({ electronic_data: line }, index) => (
              <tr key={index}>
                <td>{line.text}</td>
                <td>
                  {line.quantity} {line.unit}
                </td>
                <td>{line.unit_price} EUR</td>
                <td>
                  {line.tax_category} · {line.tax_rate} %
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="actions">
        {canEdit && invoice.status === 'draft' && (
          <>
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              {t('Bearbeiten')}
            </button>
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => setReport(await einvoiceApi.validate(org.id, id)))
              }
            >
              {t('E-Rechnung prüfen')}
            </button>
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => void act(() => billingApi.finalize(org.id, id))}
            >
              {t('Prüfen und festschreiben')}
            </button>
          </>
        )}
        <a
          className="button button-ghost"
          href={billingApi.pdfUrl(org.id, id)}
          target="_blank"
          rel="noreferrer"
        >
          {t('Lesbare Ansicht')}
        </a>
        {invoice.status !== 'draft' && (
          <>
            <a className="button button-ghost" href={einvoiceApi.xml(org.id, id)}>
              {t('XRechnung herunterladen')}
            </a>
            <a className="button button-ghost" href={einvoiceApi.report(org.id, id)}>
              {t('Prüfbericht herunterladen')}
            </a>
          </>
        )}
        {invoice.status === 'cancelled' && (
          <a className="button button-ghost" href={einvoiceApi.xml(org.id, id, true)}>
            {t('Stornorechnung herunterladen')}
          </a>
        )}
        <Link className="button button-ghost" to={`/finanzen/rechnungen?rechnung=${id}`}>
          {t('Zahlungen und Versand')}
        </Link>
      </div>
      {invoice.status !== 'draft' && (
        <InvoiceDocumentsPanel
          org={org.id}
          invoice={invoice}
          canEdit={canEdit}
          reload={load.reload}
        />
      )}
    </div>
  )
}

function AdvanceSelection({
  org,
  value,
  update,
}: {
  org: number
  value: CommercialInput
  update: (ids: number[]) => void
}) {
  const load = useLoad(
    () =>
      value.partner ? einvoiceApi.advances(org, value.partner, value.project) : Promise.resolve([]),
    [org, value.partner, value.project],
  )
  const selected = value.advance_invoices ?? []
  return (
    <section className="subcard stack">
      <h3>{t('Bereits vereinnahmte Anzahlungen')}</h3>
      <p className="muted">
        {t(
          'Erfasse die gesamte Leistung. Ausgewählte Zahlungseingänge werden einmalig vom Zahlbetrag abgezogen; es entsteht keine zweite Einnahme.',
        )}
      </p>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {load.data?.map((row) => (
        <Checkbox
          key={row.id}
          label={`${row.number} · ${euro(row.paid)}`}
          checked={selected.includes(row.id)}
          onChange={(checked) =>
            update(checked ? [...selected, row.id] : selected.filter((id) => id !== row.id))
          }
        />
      ))}
      {load.data?.length === 0 && (
        <p>
          {t(
            'Keine passenden bezahlten Anzahlungsrechnungen vorhanden. Auftraggeber und Veranstaltung müssen übereinstimmen.',
          )}
        </p>
      )}
    </section>
  )
}

export function CommercialForm({
  invoice,
  onSaved,
  onClose,
  seed,
  saveDraft,
}: {
  invoice?: CommercialInvoice
  onSaved: (id: number) => void
  onClose: () => void
  seed?: Partial<CommercialInput>
  saveDraft?: (value: CommercialInput, key: string) => Promise<CommercialInvoice>
}) {
  const org = useActiveOrg()
  const partners = useLoad(() => einvoiceApi.partners(org.id), [org.id])
  const settings = useLoad(() => billingApi.settings(org.id), [org.id])
  const projects = useLoad(
    () =>
      org.modules.includes('finance') && org.permissions.includes('finance.view')
        ? financeApi.projects(org.id)
        : Promise.resolve([]),
    [org.id],
  )
  const [requestKey] = useState(newRequestKey)
  const [today] = useState(todayIso)
  const [value, setValue] = useState<CommercialInput>(() =>
    invoice
      ? {
          ...invoice.electronic_data,
          document_kind: invoice.document_kind ?? 'invoice',
          advance_invoices: invoice.advance_invoices ?? [],
          partner: invoice.partner,
          payment_category: invoice.payment_category,
          date: invoice.date,
          due_date: invoice.due_date,
          subject: invoice.subject,
          note: invoice.note,
          project: invoice.project,
          lines: invoice.lines.map((line) => line.electronic_data),
        }
      : {
          document_kind: 'invoice',
          advance_invoices: [],
          partner: 0,
          payment_category: 0,
          date: today,
          due_date: today,
          subject: '',
          note: '',
          project: null,
          seller: { ...emptyParty(), name: org.name },
          buyer: emptyParty(),
          buyer_reference: '',
          order_reference: '',
          service_start: today,
          service_end: today,
          iban: '',
          currency: 'EUR',
          lines: [blankLine()],
          ...seed,
        },
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const update = <K extends keyof CommercialInput>(key: K, data: CommercialInput[K]) =>
    setValue({ ...value, [key]: data })
  const [initial] = useState(() => JSON.stringify(value))
  useDraftGuard(JSON.stringify(value) !== initial)
  const lineChange = (index: number, patch: Partial<CommercialLine>) =>
    update(
      'lines',
      value.lines.map((line, at) => (at === index ? { ...line, ...patch } : line)),
    )
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          const saved = saveDraft
            ? await saveDraft(value, requestKey)
            : await einvoiceApi.save(org.id, value, requestKey, invoice?.id)
          onSaved(saved.id)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{t('Leistungsrechnung')}</h2>
      <Why k="einv_service_period" />
      <p className="muted small">
        <Term k="advance_invoice">{t('Anzahlungsrechnung')}</Term>
        {' · '}
        <Term k="leitweg_id">{t('Leitweg-ID')}</Term>
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {partners.error && <Alert kind="error">{partners.error}</Alert>}
      <fieldset disabled={busy} className="stack">
        {
          <SelectField
            label={t('Rechnungsart')}
            value={value.document_kind ?? 'invoice'}
            onChange={(e) =>
              setValue({
                ...value,
                document_kind: e.target.value as CommercialInput['document_kind'],
                advance_invoices: [],
              })
            }
          >
            <option value="invoice">{t('Rechnung')}</option>
            {!saveDraft && <option value="advance">{t('Anzahlungsrechnung')}</option>}
            <option value="final">{t('Schlussrechnung')}</option>
          </SelectField>
        }
        {value.document_kind === 'final' && (
          <AdvanceSelection
            org={org.id}
            value={value}
            update={(ids) => update('advance_invoices', ids)}
          />
        )}
        {settings.error && <Alert kind="error">{settings.error}</Alert>}
        <SelectField
          label={t('Kategorie für Zahlungseingänge')}
          required
          value={value.payment_category || ''}
          onChange={(e) => update('payment_category', Number(e.target.value))}
        >
          <option value="">{t('Bitte wählen')}</option>
          {settings.data?.categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </SelectField>
        {(projects.data?.length ?? 0) > 0 && (
          <SelectField
            label={t('Veranstaltung')}
            value={value.project ?? ''}
            onChange={(e) => update('project', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">—</option>
            {projects.data?.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField
          label={t('Geschäftspartner')}
          required
          value={value.partner || ''}
          onChange={(e) => {
            const partner = partners.data?.find((item) => item.id === Number(e.target.value))
            if (partner) setValue({ ...value, partner: partner.id, buyer: partner.details })
          }}
        >
          <option value="">{t('Bitte wählen')}</option>
          {partners.data
            ?.filter((p) => p.is_active && p.is_customer)
            .map((partner) => (
              <option key={partner.id} value={partner.id}>
                {partner.name}
              </option>
            ))}
        </SelectField>
        <Link to="/finanzen/geschaeftspartner">{t('Geschäftspartner verwalten')}</Link>
        <div className="form-grid">
          <Field
            label={t('Betreff')}
            required
            value={value.subject}
            onChange={(e) => update('subject', e.target.value)}
          />
          <Field
            label={t('Rechnungsdatum')}
            type="date"
            required
            value={value.date}
            onChange={(e) => update('date', e.target.value)}
          />
          <Field
            label={t('Fällig am')}
            type="date"
            required
            value={value.due_date}
            onChange={(e) => update('due_date', e.target.value)}
          />
          <Field
            label={t('Leistungsbeginn')}
            type="date"
            required
            value={value.service_start}
            onChange={(e) => update('service_start', e.target.value)}
          />
          <Field
            label={t('Leistungsende')}
            type="date"
            required
            value={value.service_end}
            onChange={(e) => update('service_end', e.target.value)}
          />
          <Field
            label={t('Käuferreferenz / Leitweg-ID')}
            required
            value={value.buyer_reference}
            onChange={(e) => update('buyer_reference', e.target.value)}
          />
          <Field
            label={t('Bestellreferenz')}
            value={value.order_reference}
            onChange={(e) => update('order_reference', e.target.value)}
          />
          <Field
            label={t('IBAN für die Zahlung')}
            required
            value={value.iban}
            onChange={(e) => update('iban', e.target.value)}
          />
          <Field
            label={t('Hinweis')}
            value={value.note}
            onChange={(e) => update('note', e.target.value)}
          />
        </div>
        <PartyFields
          title={t('Rechnungssteller')}
          value={value.seller}
          onChange={(seller) => update('seller', seller)}
        />
        <PartyFields
          title={t('Rechnungsempfänger')}
          value={value.buyer}
          onChange={(buyer) => update('buyer', buyer)}
        />
        <p>
          {t(
            'Kontaktperson und Telefonnummer des Rechnungsstellers werden für XRechnung benötigt. Alle Beträge werden in EUR erfasst.',
          )}
        </p>
        {value.lines.map((line, index) => (
          <fieldset key={index} className="subcard stack">
            <legend>
              {t('Position')} {index + 1}
            </legend>
            <div className="form-grid">
              <Field
                label={t('Bezeichnung')}
                required
                value={line.text}
                onChange={(e) => lineChange(index, { text: e.target.value })}
              />
              <Field
                label={t('Menge')}
                type="number"
                min="0.0001"
                step="0.0001"
                required
                value={line.quantity}
                onChange={(e) => lineChange(index, { quantity: e.target.value })}
              />
              <SelectField
                label={t('Einheit')}
                value={line.unit}
                onChange={(e) => lineChange(index, { unit: e.target.value })}
              >
                <option value="C62">{t('Stück')}</option>
                <option value="HUR">{t('Stunden')}</option>
                <option value="DAY">{t('Tage')}</option>
                <option value="MON">{t('Monate')}</option>
                <option value="KMT">{t('Kilometer')}</option>
                <option value="H87">{t('Einzelstück')}</option>
              </SelectField>
              <Field
                label={t('Nettopreis je Einheit')}
                type="number"
                min="0"
                step="0.000001"
                required
                value={line.unit_price}
                onChange={(e) => lineChange(index, { unit_price: e.target.value })}
              />
              <SelectField
                label={t('Steuerkategorie')}
                value={line.tax_category}
                onChange={(e) =>
                  lineChange(index, {
                    tax_category: e.target.value,
                    tax_rate: e.target.value === 'S' ? '19' : '0',
                    tax_reason: '',
                  })
                }
              >
                <option value="S">{t('Reguläre Umsatzsteuer')}</option>
                <option value="Z">{t('Nullsatz')}</option>
                <option value="E">{t('Steuerbefreit')}</option>
                <option value="AE">{t('Steuerschuldnerschaft des Empfängers')}</option>
                <option value="O">{t('Nicht steuerbar')}</option>
              </SelectField>
              <Field
                label={t('Steuersatz in Prozent')}
                type="number"
                min="0"
                max="100"
                step="0.01"
                disabled={line.tax_category !== 'S'}
                value={line.tax_rate}
                onChange={(e) => lineChange(index, { tax_rate: e.target.value })}
              />
              {['E', 'AE', 'O'].includes(line.tax_category) && (
                <Field
                  label={t('Steuerlicher Grund')}
                  required
                  value={line.tax_reason}
                  onChange={(e) => lineChange(index, { tax_reason: e.target.value })}
                />
              )}
              <Field
                label={t('Abschlag netto')}
                type="number"
                min="0"
                step="0.01"
                value={line.allowance}
                onChange={(e) => lineChange(index, { allowance: e.target.value })}
              />
              <Field
                label={t('Zuschlag netto')}
                type="number"
                min="0"
                step="0.01"
                value={line.charge}
                onChange={(e) => lineChange(index, { charge: e.target.value })}
              />
              <Field
                label={t('Grund für Zu- oder Abschlag')}
                value={line.adjustment_reason}
                onChange={(e) => lineChange(index, { adjustment_reason: e.target.value })}
              />
            </div>
            {value.lines.length > 1 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  update(
                    'lines',
                    value.lines.filter((_, at) => at !== index),
                  )
                }
              >
                {t('Position entfernen')}
              </button>
            )}
          </fieldset>
        ))}
        <button
          type="button"
          className="button button-ghost"
          onClick={() => update('lines', [...value.lines, blankLine()])}
        >
          {t('Position hinzufügen')}
        </button>
      </fieldset>
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Entwurf speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          onClick={() =>
            void confirmLeave().then((ok) => {
              if (ok) onClose()
            })
          }
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
