import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { earmarkApi } from '../../api/donations.ts'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type {
  Account,
  Booking,
  BookingKind,
  Category,
  EInvoiceInfo,
  Project,
} from '../../api/finance.ts'
import type { MemberRow } from '../../api/members.ts'
import { unitName } from '../../api/orgs.ts'
import type { DepartmentChoice } from '../../api/orgs.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { errorMessage, formatDate, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { SplitEditor } from './SplitEditor.tsx'
import { confirmDialog, promptDialog } from '../../components/dialog.ts'
import { useTerms } from '../../org/terms.ts'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { KIND_LABEL } from './bookingsHelpers.ts'
import { Receipts } from './Receipts.tsx'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function BookingForm({
  orgId,
  isClub,
  hasMembers,
  booking,
  kind,
  vatRegistered,
  accounts,
  categories,
  departments,
  projects,
  canEdit,
  onSaved,
  onClose,
}: {
  orgId: number
  isClub: boolean
  /** Modul Mitglieder an: Buchung lässt sich einem Mitglied zuordnen */
  hasMembers: boolean
  booking: Booking | null
  kind: BookingKind
  accounts: Account[]
  categories: Category[]
  departments: DepartmentChoice[]
  projects: Project[]
  /** Verein ist umsatzsteuerpflichtig: Steuersatz je Buchung anbieten */
  vatRegistered?: boolean
  canEdit: boolean
  onSaved: (b: Booking, again: boolean) => void
  onClose: () => void
}) {
  const tm = useTerms()
  const hasTax = useActiveOrg().modules.includes('tax')
  const activeAccounts = accounts.filter((a) => a.is_active || a.id === booking?.account)
  const usable = categories.filter(
    (c) => (c.is_active || c.id === booking?.category) && (c.kind === 'both' || c.kind === kind),
  )
  const form = useForm({
    number: booking ? String(booking.number) : '',
    date: booking?.date ?? today(),
    amount: booking ? booking.amount.replace('.', ',') : '',
    account: String(booking?.account ?? activeAccounts[0]?.id ?? ''),
    to_account: String(booking?.to_account ?? ''),
    category: String(booking?.category ?? ''),
    text: booking?.text ?? '',
    reference: booking?.reference ?? '',
    counterparty: booking?.counterparty ?? '',
    department: String(booking?.department ?? ''),
    project: String(booking?.project ?? ''),
    allowance: (booking?.allowance ?? '') as string,
    artist_fee: !!booking?.artist_fee,
    earmark: String(booking?.earmark ?? ''),
    vat_rate: (booking?.vat_rate ?? '') as string,
    input_tax_share: String(booking?.input_tax_share ?? 100),
  })
  // Zweckgebundene Spenden (Konzept vereinskasse-steuern, S5): nur mit Zuwendungen
  const hasDonations = useActiveOrg().modules.includes('donations')
  const earmarks = useLoad(
    () =>
      hasDonations && kind === 'expense'
        ? earmarkApi.list(orgId).catch(() => [])
        : Promise.resolve([]),
    [orgId, hasDonations, kind],
  )
  const usableEarmarks = (earmarks.data ?? []).filter(
    (x) => x.is_active || x.id === booking?.earmark,
  )
  const usableProjects = projects.filter((p) => p.status !== 'done' || p.id === booking?.project)
  const [member, setMember] = useState<MemberRow | null>(
    booking?.membership
      ? ({
          id: booking.membership,
          last_name: booking.member_name?.split(', ')[0] ?? '',
          first_name: booking.member_name?.split(', ')[1] ?? '',
        } as MemberRow)
      : null,
  )
  const [again, setAgain] = useState(false)
  const [splitting, setSplitting] = useState(false)
  // E-Rechnung: gelesene Angaben füllen das Formular, die Datei wird nach dem Buchen Beleg
  const [einvoice, setEinvoice] = useState<{ file: File; info: EInvoiceInfo } | null>(null)
  const [einvoiceError, setEinvoiceError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<
    { name: string; partner?: number; category?: number | null }[]
  >([])
  const [partner, setPartner] = useState<number | null>(booking?.partner ?? null)
  useEffect(() => {
    if (kind === 'transfer') return
    let alive = true
    financeApi
      .counterparties(orgId, kind)
      .then((rows) => alive && setSuggestions(rows))
      .catch(() => alive && setSuggestions([]))
    return () => {
      alive = false
    }
  }, [orgId, kind])
  // Bei Ausgaben ist meist ein Geschäft der Empfänger: Mitglied und Abteilung eingeklappt
  const assignedOpen = kind === 'income' || !!booking?.membership || !!booking?.department

  function pickMember(m: MemberRow | null) {
    setMember(m)
    if (m && !v.counterparty.trim()) set('counterparty', `${m.first_name} ${m.last_name}`.trim())
  }
  const { values: v, errors, set } = form
  const readOnly = !canEdit
  // Umsatzsteuer (Konzept vereinskasse-steuern, S2): mit Modul Steuern bei Steuerpflicht oder
  // wenn schon ein Satz gewählt ist
  const showVat =
    hasTax &&
    kind !== 'transfer' &&
    (vatRegistered ||
      !!booking?.vat_rate ||
      !!categories.find((c) => String(c.id) === v.category)?.vat_rate)
  function pickCategory(value: string) {
    set('category', value)
    // Neue Buchung: Vorgabe der Kategorie für die Umsatzsteuer übernehmen
    if (!booking) set('vat_rate', categories.find((c) => String(c.id) === value)?.vat_rate ?? '')
  }
  // Festgeschrieben oder Teil eines Stornos: nur noch die Veranstaltung ist änderbar
  const locked = !!booking && (booking.fixed || !!booking.cancels || !!booking.cancelled_by)

  function payloadOf(
    x: typeof v & { membership: number | null; partner: number | null },
  ): Record<string, unknown> {
    return {
      date: x.date,
      ...(booking && x.number ? { number: Number(x.number) } : {}),
      kind,
      amount: parseAmount(x.amount),
      account: Number(x.account),
      to_account: kind === 'transfer' && x.to_account ? Number(x.to_account) : null,
      category: kind !== 'transfer' && x.category ? Number(x.category) : null,
      text: x.text,
      reference: x.reference,
      counterparty: kind === 'transfer' ? '' : x.counterparty,
      partner: kind === 'transfer' ? null : x.partner,
      membership: x.membership,
      department: x.department ? Number(x.department) : null,
      project: kind !== 'transfer' && x.project ? Number(x.project) : null,
      allowance: kind === 'expense' ? x.allowance : '',
      artist_fee: kind === 'expense' && x.artist_fee,
      earmark: kind === 'expense' && x.earmark ? Number(x.earmark) : null,
      ...(kind !== 'transfer' && showVat
        ? {
            vat_rate: x.vat_rate,
            input_tax_share: Math.min(100, Math.max(0, Number(x.input_tax_share) || 0)),
          }
        : {}),
    }
  }

  // Bestehende Buchungen speichern automatisch, neue erst mit „Buchen“
  const auto = useAutoSave(
    { values: { ...v, membership: member?.id ?? null, partner }, setErrors: form.setErrors },
    (_changes, values) => financeApi.updateBooking(orgId, booking!.id, payloadOf(values)),
    {
      enabled: booking !== null && canEdit,
      onSaved: (saved) => onSaved(saved as Booking, false),
    },
  )

  async function save(e: FormEvent) {
    e.preventDefault()
    if (booking) {
      if (!(await auto.flush())) return
      onClose()
      return
    }
    const saved = await form.submit(() =>
      financeApi.createBooking(orgId, payloadOf({ ...v, membership: member?.id ?? null, partner })),
    )
    if (!saved) return
    if (einvoice) {
      try {
        await financeApi.uploadReceipt(orgId, (saved as Booking).id, einvoice.file)
      } catch (err) {
        setEinvoiceError(
          t('Gebucht, aber die E-Rechnung ist nicht angehängt: {x}. ', { x: errorMessage(err) }) +
            t('Bitte in der Buchung unter Belege erneut hinzufügen.'),
        )
        return
      }
    }
    onSaved(saved as Booking, again)
  }

  async function readEinvoice(file: File | undefined) {
    if (!file) return
    setEinvoiceError(null)
    try {
      const { einvoice: info, suggestion: s } = await financeApi.readEinvoice(orgId, file)
      if (s.date) set('date', s.date)
      set('amount', s.amount.replace('.', ','))
      set('counterparty', s.counterparty)
      set('reference', s.reference)
      set('text', s.text)
      setEinvoice({ file, info })
    } catch (err) {
      setEinvoice(null)
      setEinvoiceError(errorMessage(err))
    }
  }

  // Felder speichern automatisch; Schließen wartet nur auf die letzte Änderung
  async function close() {
    if (booking && canEdit && !(await auto.flush())) return
    onClose()
  }

  async function remove() {
    if (
      !booking ||
      !(await confirmDialog({
        final: false,
        title: t('Buchung {display_number} löschen?', { display_number: booking.display_number }),
        message: t('Löschen geht nur am Tag der Erfassung. Danach bitte stornieren.'),
        confirmLabel: t('Löschen'),
      }))
    )
      return
    const ok = await form.submit(() => financeApi.deleteBooking(orgId, booking.id))
    if (ok !== undefined) onClose()
  }

  async function storno() {
    if (!booking) return
    const reason = await promptDialog({
      title: t('Buchung {display_number} stornieren?', { display_number: booking.display_number }),
      message:
        t('Es entsteht eine Gegenbuchung mit heutigem Datum über denselben Betrag. Die Buchung ') +
        t('bleibt sichtbar und unverändert. Eine richtige Buchung legst du danach neu an.'),
      label: t('Grund'),
      confirmLabel: t('Stornieren'),
    })
    if (reason === null) return
    const saved = await form.submit(() => financeApi.stornoBooking(orgId, booking.id, reason))
    if (saved) onSaved(saved as Booking, false)
  }

  const title = booking
    ? t('{x} {display_number}', { x: KIND_LABEL[kind], display_number: booking.display_number })
    : t('Neue {x}', { x: KIND_LABEL[kind] })

  return (
    <div className="card card-wide">
      <form onSubmit={save}>
        <div className="card-head">
          <h2>{title}</h2>
          <button type="button" className="button button-ghost push-right" onClick={close}>
            {t('Schließen')}
          </button>
        </div>
        {booking?.cancelled_by && (
          <Alert kind="info">
            {t('Storniert durch Buchung {number} vom  {x}:', {
              number: booking.cancelled_by.number,
              x: formatDate(booking.cancelled_by.date),
            })}{' '}
            {booking.cancelled_by.reason}
          </Alert>
        )}
        {booking?.cancels && (
          <Alert kind="info">
            {t('Storno von Buchung {number}:', { number: booking.cancels.number })}{' '}
            {booking.cancel_reason}
          </Alert>
        )}
        {booking?.split && (
          <Alert kind="info">
            {booking.split.is_lead
              ? t(
                  'Splitbuchung: Weitere Teile sind {numbers}. Belege und Kontoumsatz gehören zu dieser Buchung.',
                  { numbers: booking.split.parts.map((p) => p.number).join(', ') },
                )
              : t(
                  'Teil der Splitbuchung {number}. Belege und Kontoumsatz stehen dort; Datum, Art und Konto gelten für alle Teile.',
                  { number: booking.split.lead.number },
                )}
          </Alert>
        )}
        {booking?.fixed && !booking.cancels && !booking.cancelled_by && (
          <>
            <Alert kind="info">
              {t(
                'Die Buchung ist festgeschrieben und lässt sich nicht mehr ändern. Ist sie falsch, bitte stornieren und neu buchen.',
              )}
            </Alert>
            <Why k="booking_fixed" />
          </>
        )}
        {!booking && kind === 'expense' && canEdit && (
          <div className="einvoice-read">
            <label className="button button-ghost file-button">
              {t('E-Rechnung einlesen (XML oder ZUGFeRD-PDF)')}
              <input
                type="file"
                accept=".xml,application/xml,text/xml,application/pdf"
                className="file-input"
                onChange={(e) => {
                  void readEinvoice(e.target.files?.[0])
                  e.target.value = ''
                }}
              />
            </label>
            {einvoice && (
              <Alert kind="info">
                {t(
                  'E-Rechnung {number} von {seller} über  {x} gelesen. Bitte Konto und Kategorie wählen; die Datei wird beim Buchen als Beleg angehängt.',
                  {
                    number: einvoice.info.number,
                    seller: einvoice.info.seller,
                    x: euro(einvoice.info.payable),
                  },
                )}
              </Alert>
            )}
            {einvoiceError && <Alert kind="error">{einvoiceError}</Alert>}
            <p className="muted small">
              {t('Eine')} <Term k="e_invoice">{t('E-Rechnung')}</Term>{' '}
              {t('füllt die Buchung vor und wird unverändert als Beleg aufbewahrt.')}
            </p>
          </div>
        )}
        <fieldset disabled={readOnly || form.busy || locked}>
          <div className="grid-3">
            {booking && (
              <Field
                label={t('Buchungsnummer')}
                type="number"
                min={1}
                required
                value={v.number}
                error={errors.number}
                hint={t('Korrektur möglich, solange die Nummer frei ist')}
                onChange={(e) => set('number', e.target.value)}
              />
            )}
            <Field
              label={t('Datum')}
              type="date"
              required
              value={v.date}
              error={errors.date}
              onChange={(e) => set('date', e.target.value)}
            />
            <Field
              label={t('Betrag (€)')}
              inputMode="decimal"
              required
              placeholder="0,00"
              value={v.amount}
              error={errors.amount}
              onChange={(e) => set('amount', e.target.value)}
            />
            {kind !== 'transfer' && (
              <Field
                label={
                  kind === 'expense' ? t('Empfänger (Geschäft, Dienstleister …)') : t('Zahler')
                }
                suggestions={suggestions.map((s) => ({ value: s.name }))}
                placeholder={
                  kind === 'expense' ? t('z. B. Getränkehandel') : t('z. B. Name oder Firma')
                }
                value={v.counterparty}
                error={errors.counterparty}
                hint={partner ? t('Geschäftspartner verknüpft') : undefined}
                onChange={(e) => {
                  const name = e.target.value
                  set('counterparty', name)
                  // Gewählter Geschäftspartner: verknüpfen und Standardkategorie vorschlagen
                  const hit = suggestions.find((s) => s.partner && s.name === name)
                  setPartner(hit?.partner ?? null)
                  if (hit?.category && !v.category) set('category', String(hit.category))
                }}
              />
            )}
            <SelectField
              label={kind === 'transfer' ? t('von Konto') : t('Konto')}
              value={v.account}
              error={errors.account}
              onChange={(e) => set('account', e.target.value)}
            >
              {activeAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </SelectField>
            {kind === 'transfer' ? (
              <SelectField
                label={t('auf Konto')}
                value={v.to_account}
                error={errors.to_account}
                onChange={(e) => set('to_account', e.target.value)}
              >
                <option value="">{t('bitte wählen')}</option>
                {activeAccounts
                  .filter((a) => String(a.id) !== v.account)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
              </SelectField>
            ) : (
              <SelectField
                label={t('Kategorie')}
                value={v.category}
                error={errors.category}
                onChange={(e) => pickCategory(e.target.value)}
              >
                <option value="">{t('bitte wählen')}</option>
                {usable.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </SelectField>
            )}
            <Field
              label={t('Buchungstext')}
              required
              value={v.text}
              error={errors.text}
              onChange={(e) => set('text', e.target.value)}
            />
            <Field
              label={t('Belegnummer/Referenz')}
              value={v.reference}
              error={errors.reference}
              onChange={(e) => set('reference', e.target.value)}
            />
            {showVat && (
              <SelectField
                label={t('Umsatzsteuer im Betrag')}
                value={v.vat_rate}
                error={errors.vat_rate}
                onChange={(e) => set('vat_rate', e.target.value)}
              >
                <option value="">{t('keine (nicht steuerbar)')}</option>
                <option value="19">{t('19 %')}</option>
                <option value="7">{t('7 %')}</option>
                <option value="exempt">{t('steuerfrei')}</option>
              </SelectField>
            )}
            {showVat && kind === 'expense' && (v.vat_rate === '19' || v.vat_rate === '7') && (
              <Field
                label={t('Vorsteuer abziehbar (%)')}
                term="input_tax"
                hint={t('Bei gemischt genutzten Ausgaben den unternehmerischen Anteil.')}
                type="number"
                min={0}
                max={100}
                value={v.input_tax_share}
                error={errors.input_tax_share}
                onChange={(e) => set('input_tax_share', e.target.value)}
              />
            )}
            {kind === 'expense' && (hasTax || !!booking?.allowance) && (
              <SelectField
                label={t('Aufwandsvergütung an eine Person')}
                value={v.allowance}
                error={errors.allowance}
                onChange={(e) => set('allowance', e.target.value)}
              >
                <option value="">{t('keine')}</option>
                <option value="trainer">{t('Übungsleiterfreibetrag (§ 3 Nr. 26 EStG)')}</option>
                <option value="volunteer">{t('Ehrenamtspauschale (§ 3 Nr. 26a EStG)')}</option>
              </SelectField>
            )}
            {kind === 'expense' && (hasTax || !!booking?.artist_fee) && (
              <Checkbox
                label={t('Honorar an Künstler (Künstlersozialabgabe)')}
                checked={v.artist_fee}
                onChange={(value) => set('artist_fee', value)}
              />
            )}
            {kind === 'expense' && usableEarmarks.length > 0 && (
              <SelectField
                label={t('Zweckgebundene Spende verwendet für')}
                value={v.earmark}
                error={errors.earmark}
                onChange={(e) => set('earmark', e.target.value)}
              >
                <option value="">{t('keine')}</option>
                {usableEarmarks.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </SelectField>
            )}
          </div>
          {kind !== 'transfer' && usableProjects.length > 0 && !locked && (
            <div className="grid-2">
              <SelectField
                label={t('Veranstaltung (optional)')}
                value={v.project}
                error={errors.project}
                onChange={(e) => set('project', e.target.value)}
              >
                <option value="">{t('keine')}</option>
                {usableProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </SelectField>
            </div>
          )}
          {kind !== 'transfer' && isClub && (hasMembers || departments.length > 0) && (
            <details className="booking-assign" open={assignedOpen}>
              <summary>
                {hasMembers
                  ? t('Mitglied oder {sg} zuordnen', { sg: tm.sg })
                  : t('{sg} zuordnen', { sg: tm.sg })}{' '}
                <span className="muted">{t('(optional)')}</span>
              </summary>
              <div className="grid-2">
                {/* Ohne Modul Mitglieder gibt es keine Mitgliedersuche (sonst 404) */}
                {hasMembers && <MemberPicker orgId={orgId} value={member} onChange={pickMember} />}
                {departments.length > 0 && (
                  <SelectField
                    label={t('{sg} (optional)', { sg: tm.sg })}
                    value={v.department}
                    onChange={(e) => set('department', e.target.value)}
                  >
                    <option value="">{t('keine')}</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {unitName(d)}
                      </option>
                    ))}
                  </SelectField>
                )}
              </div>
            </details>
          )}
          {usable.length === 0 && kind !== 'transfer' && (
            <Alert kind="info">
              {kind === 'income'
                ? t('Für Einnahmen gibt es noch keine Kategorie. Bitte unter')
                : t('Für Ausgaben gibt es noch keine Kategorie. Bitte unter')}{' '}
              <Link to="/finanzen/einrichtung/kategorien">
                {t('Finanzen → Einrichtung → Kategorien')}
              </Link>{' '}
              {t('anlegen.')}
            </Alert>
          )}
        </fieldset>
        {locked && canEdit && kind !== 'transfer' && usableProjects.length > 0 && (
          <div className="grid-2">
            <SelectField
              label={t('Veranstaltung (optional)')}
              value={v.project}
              error={errors.project}
              disabled={form.busy}
              onChange={(e) => set('project', e.target.value)}
            >
              <option value="">{t('keine')}</option>
              {usableProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </SelectField>
          </div>
        )}
        {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
        {booking && canEdit && <SaveStatus auto={auto} />}
        {canEdit && (
          <div className="button-row">
            {!booking && (
              <button type="submit" className="button button-primary" disabled={form.busy}>
                {t('Buchen')}
              </button>
            )}
            {!booking && (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={again}
                  onChange={(e) => setAgain(e.target.checked)}
                />
                <span>
                  {t('danach nächste')} {KIND_LABEL[kind]} {t('erfassen')}
                </span>
              </label>
            )}
            {booking && kind !== 'transfer' && !locked && !booking.split && !splitting && (
              <button
                type="button"
                className="button button-ghost"
                disabled={form.busy}
                onClick={() => setSplitting(true)}
              >
                {t('Aufteilen')}
              </button>
            )}
            {booking &&
              hasTax &&
              kind === 'expense' &&
              !booking.cancels &&
              !booking.cancelled_by &&
              Number(booking.amount) >= 250 && (
                <Link
                  className="button button-ghost"
                  to={`/finanzen/anlagen?${new URLSearchParams({
                    buchung: String(booking.id),
                    betrag: booking.amount,
                    datum: booking.date,
                    name: booking.text,
                  }).toString()}`}
                >
                  {t('Als Anlage erfassen')}
                </Link>
              )}
            {booking && !booking.cancels && !booking.cancelled_by && (
              <button
                type="button"
                className="button button-ghost push-right"
                disabled={form.busy}
                onClick={() => void storno()}
              >
                {t('Stornieren')}
              </button>
            )}
            {booking?.deletable && (
              <button type="button" className="button button-danger" onClick={remove}>
                {t('Löschen')}
              </button>
            )}
          </div>
        )}
      </form>
      {booking && splitting && (
        <SplitEditor
          orgId={orgId}
          booking={booking}
          categories={usable}
          projects={usableProjects}
          onCancel={() => setSplitting(false)}
          onDone={(lead) => {
            setSplitting(false)
            onSaved(lead, false)
          }}
        />
      )}
      {booking ? (
        <Receipts orgId={orgId} booking={booking} canEdit={canEdit} />
      ) : (
        <p className="muted small">{t('Belege kannst du nach dem Speichern anhängen.')}</p>
      )}
    </div>
  )
}
