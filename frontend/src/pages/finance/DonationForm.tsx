import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { donationApi, earmarkApi } from '../../api/donations.ts'
import type {
  Donation,
  DonationInput,
  DonationKind,
  DonationSettings,
  GoodsOrigin,
} from '../../api/donations.ts'
import { parseAmount } from '../../api/finance.ts'
import type { MemberRow } from '../../api/members.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { fieldErrors } from './donationsHelpers.ts'

const KIND_LABEL: Record<DonationKind, string> = {
  money: t('Geldzuwendung'),
  fee: t('Mitgliedsbeitrag'),
  goods: t('Sachzuwendung'),
}

const ORIGIN_LABEL: Record<Exclude<GoodsOrigin, ''>, string> = {
  private: t('aus dem Privatvermögen'),
  business: t('aus dem Betriebsvermögen'),
  unknown: t('keine Angaben trotz Nachfrage'),
}

/** Heutiges Datum in Ortszeit (nicht UTC), auch kurz nach Mitternacht (UX-Audit 31.10. N09) */
function today() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// Felder mit eigener Fehleranzeige im Formular; alle anderen Fehler stehen gesammelt darunter
const SHOWN_FIELDS = new Set([
  'kind',
  'date',
  'amount',
  'donor_name',
  'goods_description',
  'goods_origin',
])

export function DonationForm({
  initial,
  settings,
  onDirty,
  onCancel,
  onDone,
}: {
  initial: Donation | null
  settings: DonationSettings | null
  onDirty: (dirty: boolean) => void
  onCancel: () => void
  onDone: (text: string) => Promise<void>
}) {
  const org = useActiveOrg()
  const [v, setV] = useState<Partial<DonationInput>>(
    initial ?? {
      date: today(),
      kind: 'money',
      waiver: false,
      allowance: '',
      membership: null,
      donor_name: '',
      donor_address: '',
      goods_description: '',
      goods_origin: '',
      goods_documents: false,
      note: '',
      earmark: null,
    },
  )
  const earmarks = useLoad(() => earmarkApi.list(org.id).catch(() => []), [org.id])
  const usableEarmarks = (earmarks.data ?? []).filter(
    (x) => x.is_active || x.id === initial?.earmark,
  )
  // Betrag und Datum folgen der Buchung (Datenaudit 08.11. DA-03)
  const fromBooking = !!initial?.booking
  const [amountText, setAmountText] = useState(initial ? initial.amount.replace('.', ',') : '')
  const [member, setMember] = useState<MemberRow | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof DonationInput>(k: K, value: DonationInput[K]) =>
    setV((old) => ({ ...old, [k]: value }))
  const goods = v.kind === 'goods'
  // Ungespeicherte Eingaben schützen (UX-Audit 31.10. W01)
  const [saved, setSaved] = useState(false)
  const { dirty } = useChangesGuard([v, amountText], !saved)
  useEffect(() => onDirty(dirty), [dirty, onDirty])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    setFailure(null)
    const data = { ...v, amount: parseAmount(amountText) }
    try {
      if (initial) await donationApi.update(org.id, initial.id, data)
      else await donationApi.create(org.id, data)
      setSaved(true)
      await onDone(initial ? t('Zuwendung geändert.') : t('Zuwendung erfasst.'))
    } catch (err) {
      setErrors(fieldErrors(err))
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="subcard" onSubmit={submit}>
      <h3>{initial ? t('Zuwendung ändern') : t('Zuwendung erfassen')}</h3>
      <div className="grid-3">
        <SelectField
          label={t('Art')}
          value={v.kind}
          onChange={(e) => {
            const kind = e.target.value as DonationKind
            // Verzicht gibt es nur bei Geld: beim Wechsel zur Sache mit abschalten (N04)
            setV((old) => ({
              ...old,
              kind,
              waiver: kind === 'goods' ? false : old.waiver,
              allowance: kind === 'goods' ? '' : old.allowance,
            }))
          }}
          error={errors.kind}
        >
          <option value="money">{KIND_LABEL.money}</option>
          {(settings?.fees_allowed || v.kind === 'fee') && (
            <option value="fee">{KIND_LABEL.fee}</option>
          )}
          <option value="goods">{KIND_LABEL.goods}</option>
        </SelectField>
        <Field
          label={t('Tag der Zuwendung')}
          type="date"
          value={v.date ?? ''}
          onChange={(e) => set('date', e.target.value)}
          error={errors.date}
          hint={
            fromBooking
              ? t('Betrag und Datum folgen der Buchung {booking_number}.', {
                  booking_number: initial?.booking_number ?? '',
                })
              : undefined
          }
          required
        />
        <Field
          label={goods ? t('Wert in €') : t('Betrag in €')}
          inputMode="decimal"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          error={errors.amount}
          required
        />
      </div>
      {!initial && (
        <MemberPicker
          orgId={org.id}
          value={member}
          onChange={(m) => {
            setMember(m)
            set('membership', m?.id ?? null)
            // Name und Anschrift ergänzt der Server aus dem Mitglied
            if (m) setV((old) => ({ ...old, membership: m.id, donor_name: '', donor_address: '' }))
          }}
          label={t('Mitglied (optional)')}
        />
      )}
      {!member && (
        <div className="grid-2">
          <Field
            label={t('Name des Zuwendenden')}
            value={v.donor_name ?? ''}
            onChange={(e) => set('donor_name', e.target.value)}
            error={errors.donor_name}
            maxLength={200}
            required={!v.membership}
          />
          <label className="field">
            <span>{t('Anschrift')}</span>
            <textarea
              rows={2}
              value={v.donor_address ?? ''}
              maxLength={500}
              onChange={(e) => set('donor_address', e.target.value)}
            />
          </label>
        </div>
      )}
      {goods ? (
        <>
          <label className={`field${errors.goods_description ? ' field-invalid' : ''}`}>
            <span>{t('Genaue Bezeichnung der Sache (Alter, Zustand, Kaufpreis)')}</span>
            <textarea
              rows={2}
              value={v.goods_description ?? ''}
              maxLength={1000}
              onChange={(e) => set('goods_description', e.target.value)}
            />
            {errors.goods_description && (
              <small className="field-error">{errors.goods_description}</small>
            )}
          </label>
          <SelectField
            label={t('Herkunft')}
            value={v.goods_origin ?? ''}
            onChange={(e) => set('goods_origin', e.target.value as GoodsOrigin)}
            error={errors.goods_origin}
          >
            <option value="">{t('bitte wählen')}</option>
            {Object.entries(ORIGIN_LABEL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </SelectField>
          <Checkbox
            label={t('Unterlagen zur Wertermittlung liegen vor (z. B. Rechnung, Gutachten)')}
            checked={!!v.goods_documents}
            onChange={(on) => set('goods_documents', on)}
          />
          <Why k="donation_goods" />
        </>
      ) : (
        <Checkbox
          label={t('Verzicht auf Erstattung von Aufwendungen')}
          hint={t('z. B. Fahrtkosten, auf deren Erstattung jemand verzichtet')}
          checked={!!v.waiver}
          onChange={(on) =>
            setV((old) => ({ ...old, waiver: on, allowance: on ? old.allowance : '' }))
          }
        />
      )}
      {!goods && (
        <>
          <p className="muted small">
            {t('Ein solcher Verzicht ist eine')}{' '}
            <Term k="expense_donation">{t('Aufwandsspende')}</Term>.
          </p>
          <Why k="donation_waiver" />
        </>
      )}
      {!goods && v.waiver && (org.modules.includes('tax') || !!v.allowance) && (
        <SelectField
          label={t('Verzicht auf eine Pauschale')}
          hint={t(
            'Der Betrag zählt dann wie eine Auszahlung gegen den Freibetrag der Person (Finanzen › Pauschalen).',
          )}
          value={v.allowance ?? ''}
          onChange={(e) => set('allowance', e.target.value as DonationInput['allowance'])}
        >
          <option value="">{t('keine Pauschale (z. B. Fahrtkosten)')}</option>
          <option value="trainer">{t('Übungsleiterfreibetrag (§ 3 Nr. 26 EStG)')}</option>
          <option value="volunteer">{t('Ehrenamtspauschale (§ 3 Nr. 26a EStG)')}</option>
        </SelectField>
      )}
      {usableEarmarks.length > 0 && (
        <SelectField
          label={t('Zweckgebunden für')}
          value={v.earmark ? String(v.earmark) : ''}
          onChange={(e) => set('earmark', e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{t('nicht zweckgebunden')}</option>
          {usableEarmarks.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </SelectField>
      )}
      <Field
        label={t('Notiz (nur intern)')}
        value={v.note ?? ''}
        maxLength={300}
        onChange={(e) => set('note', e.target.value)}
      />
      {failure && <Alert kind="error">{failure}</Alert>}
      {Object.entries(errors)
        .filter(([key]) => !SHOWN_FIELDS.has(key))
        .map(([key, text]) => (
          // Fehler ohne sichtbares Feld trotzdem zeigen (UX-Audit 31.10. N04)
          <Alert key={key} kind="error">
            {text}
          </Alert>
        ))}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          onClick={() => void confirmDiscard(dirty).then((ok) => ok && onCancel())}
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

// --- Bestätigungen ---
