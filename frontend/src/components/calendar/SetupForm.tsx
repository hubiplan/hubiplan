import { useState } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type {
  BoardRegistrations,
  CancelRule,
  PriceInput,
  SetupInput,
} from '../../api/registrations.ts'
import { financeApi, parseAmount } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../ui.tsx'
import { confirmDialog } from '../dialog.ts'
import { AddOnsEditor, QuestionsEditor } from './RegistrationExtras.tsx'
import { addonInputs, cleanAddons, questionInputs } from './extras.ts'
import { berlin, toApi } from './time.ts'
import { t } from '../../i18n/index.ts'

function emptyPrice(): PriceInput {
  return {
    id: null,
    name: '',
    name_en: '',
    applies: 'all',
    age_from: null,
    age_to: null,
    capacity: null,
    vat_rate: null,
    is_active: true,
    steps: [{ name: '', amount: '', until_date: null, until_count: null }],
  }
}

function num(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

export function SetupForm({
  base,
  event,
  data,
  onCancel,
  onSaved,
}: {
  base: CalendarBase
  event: EventDetail
  data: BoardRegistrations
  onCancel: () => void
  onSaved: (data: BoardRegistrations) => void
}) {
  const offer = data.offer
  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)
  const categories = useLoad(
    () => (orgId ? financeApi.categories(orgId) : Promise.resolve([])),
    [orgId],
  )
  const close = offer ? berlin(offer.closes_at) : berlin(event.starts_at)
  const open = offer?.opens_at ? berlin(offer.opens_at) : null
  const [v, setV] = useState({
    closes_date: close.date,
    closes_time: offer ? close.time : '23:59',
    opens_date: open?.date ?? '',
    opens_time: open?.time ?? '00:00',
    is_open: offer?.is_open ?? true,
    capacity: offer?.capacity ? String(offer.capacity) : '',
    max_persons: String(offer?.max_persons ?? 6),
    guests_allowed: offer?.guests_allowed ?? true,
    due_days: String(offer?.due_days ?? 14),
    category: offer?.category ? String(offer.category) : '',
    terms: offer?.terms ?? '',
    waitlist: offer?.waitlist ?? false,
    substitute_allowed: offer?.substitute_allowed ?? true,
    cancel_fee_fixed: offer?.cancel_fee_fixed ? offer.cancel_fee_fixed.replace('.', ',') : '',
    expire_unpaid_days: offer?.expire_unpaid_days ? String(offer.expire_unpaid_days) : '',
    catering: offer?.catering ?? false,
    minors: offer?.minors ?? false,
    public: offer?.public ?? false,
    club_registration: offer?.club_registration ?? false,
  })
  const [addons, setAddons] = useState(() => addonInputs(offer))
  const [questions, setQuestions] = useState(() => questionInputs(offer))
  const healthAllowed = v.catering || addons.some((a) => a.is_active && a.kind === 'meal')
  const dropsHealth =
    !healthAllowed && (offer?.questions ?? []).some((q) => q.kind === 'health' && q.is_active)
  const [rules, setRules] = useState<CancelRule[]>(offer?.cancel_rules ?? [])
  const [prices, setPrices] = useState<PriceInput[]>(
    offer
      ? offer.prices.map((p) => ({
          id: p.id,
          name: p.name,
          name_en: p.name_en,
          applies: p.applies,
          age_from: p.age_from,
          age_to: p.age_to,
          capacity: p.capacity,
          vat_rate: p.vat_rate,
          is_active: p.is_active,
          steps: (p.steps ?? []).map((s) => ({
            name: s.name,
            amount: s.amount.replace('.', ','),
            until_date: s.until_date,
            until_count: s.until_count,
          })),
        }))
      : [emptyPrice()],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setPrice = (i: number, patch: Partial<PriceInput>) =>
    setPrices(prices.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  const setStep = (i: number, k: number, patch: Partial<PriceInput['steps'][number]>) =>
    setPrice(i, { steps: prices[i].steps.map((s, j) => (j === k ? { ...s, ...patch } : s)) })

  async function save() {
    setBusy(true)
    setError(null)
    const input: SetupInput = {
      closes_at: toApi(v.closes_date, v.closes_time || '23:59'),
      opens_at: v.opens_date ? toApi(v.opens_date, v.opens_time || '00:00') : null,
      is_open: v.is_open,
      capacity: num(v.capacity),
      max_persons: Number(v.max_persons) || 1,
      guests_allowed: v.guests_allowed,
      due_days: Number(v.due_days) || 0,
      category: v.category ? Number(v.category) : null,
      terms: v.terms,
      waitlist: v.waitlist,
      substitute_allowed: v.substitute_allowed,
      cancel_rules: rules.filter((x) => x.days > 0),
      cancel_fee_fixed: v.cancel_fee_fixed.trim() ? parseAmount(v.cancel_fee_fixed) || '0' : null,
      expire_unpaid_days: num(v.expire_unpaid_days),
      catering: v.catering,
      minors: v.minors,
      public: v.public && event.visibility === 'public',
      ...(data.club_registration_possible ? { club_registration: v.club_registration } : {}),
      addons: cleanAddons(addons),
      questions: questions
        .filter((q) => healthAllowed || q.kind !== 'health')
        .map((q) => ({ ...q, text: q.text.trim(), choices: q.choices.filter((c) => c.trim()) })),
      prices: prices.map((p, i) => ({
        ...p,
        steps: p.steps.map((s, k) => ({
          ...s,
          amount: parseAmount(s.amount) || '0',
          // die letzte Stufe gilt bis zum Anmeldeschluss
          until_date: k === p.steps.length - 1 ? null : s.until_date || null,
          until_count: k === p.steps.length - 1 ? null : s.until_count,
        })),
        name: p.name.trim() || t('Tarif {n}', { n: i + 1 }),
      })),
    }
    try {
      onSaved(await registrationApi.save(base, event.id, input))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (
      !(await confirmDialog({
        final: false,
        title: t('Anmeldung vom Termin entfernen?'),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    try {
      await registrationApi.remove(base, event.id)
      onSaved({ ...data, offer: null, registrations: [] })
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const income = (categories.data ?? []).filter((c) => c.kind === 'income')
  return (
    <div className="stack">
      {error && <Alert kind="error">{error}</Alert>}
      {!data.can_set_prices && (
        <Alert kind="info">
          {t(
            'Preise legt fest, wer Rechnungen bearbeiten darf. Ohne dieses Recht sind nur kostenlose Tarife möglich.',
          )}
        </Alert>
      )}
      <div className="form-grid">
        <Field
          label={t('Anmeldeschluss')}
          type="date"
          value={v.closes_date}
          onChange={(e) => setV({ ...v, closes_date: e.target.value })}
        />
        <Field
          label={t('Uhrzeit')}
          type="time"
          value={v.closes_time}
          onChange={(e) => setV({ ...v, closes_time: e.target.value })}
        />
        <Field
          label={t('Anmeldung ab (optional)')}
          type="date"
          value={v.opens_date}
          onChange={(e) => setV({ ...v, opens_date: e.target.value })}
        />
        <Field
          label={t('Plätze (leer: unbegrenzt)')}
          type="number"
          min={1}
          value={v.capacity}
          onChange={(e) => setV({ ...v, capacity: e.target.value })}
        />
        <Field
          label={t('Personen je Anmeldung')}
          type="number"
          min={1}
          max={20}
          value={v.max_persons}
          onChange={(e) => setV({ ...v, max_persons: e.target.value })}
        />
        <Field
          label={t('Zahlungsziel in Tagen')}
          type="number"
          min={0}
          max={90}
          value={v.due_days}
          onChange={(e) => setV({ ...v, due_days: e.target.value })}
        />
        <SelectField
          label={t('Kategorie in der Kasse')}
          value={v.category}
          onChange={(e) => setV({ ...v, category: e.target.value })}
          hint={t('leer: Kategorie für Zahlungen aus der Einrichtung')}
        >
          <option value="">{t('Vorgabe')}</option>
          {income.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
      </div>
      <Checkbox
        label={t('Mitglieder dürfen Gäste mit anmelden')}
        checked={v.guests_allowed}
        onChange={(x) => setV({ ...v, guests_allowed: x })}
      />
      {offer && (
        <Checkbox
          label={t('Anmeldung offen')}
          hint={t('ausschalten, um vor dem Anmeldeschluss zu schließen')}
          checked={v.is_open}
          onChange={(x) => setV({ ...v, is_open: x })}
        />
      )}
      <label className="field">
        <span>{t('Teilnahmebedingungen (optional)')}</span>
        <textarea
          rows={4}
          maxLength={5000}
          value={v.terms}
          onChange={(e) => setV({ ...v, terms: e.target.value })}
        />
      </label>
      <h4>{t('Warteliste und Abmeldung')}</h4>
      <Checkbox
        label={t('Warteliste, wenn alle Plätze vergeben sind')}
        hint={t(
          'Wird ein Platz frei, rückt die nächste Anmeldung automatisch verbindlich nach und bekommt die Rechnung. Nachgerückte können sich 48 Stunden lang kostenfrei abmelden.',
        )}
        checked={v.waitlist}
        onChange={(x) => setV({ ...v, waitlist: x })}
      />
      <Checkbox
        label={t('Mitglieder dürfen eine Ersatzperson eintragen')}
        hint={t('zum selben Tarif und Preis; die Rechnung bleibt')}
        checked={v.substitute_allowed}
        onChange={(x) => setV({ ...v, substitute_allowed: x })}
      />
      <p className="muted small">
        {t(
          'Stornogebühren nach den Teilnahmebedingungen: Prozent des Betrags, wenn weniger als die genannten Tage bis zum Beginn bleiben. Ohne Stufen ist das Abmelden bis zum Anmeldeschluss kostenfrei. Rückt jemand von der Warteliste nach oder wird der Termin abgesagt, entfällt die Gebühr.',
        )}
      </p>
      {rules.map((rule, i) => (
        <div key={i} className="form-grid">
          <Field
            label={t('weniger als … Tage vorher')}
            type="number"
            min={1}
            max={365}
            value={rule.days || ''}
            onChange={(e) =>
              setRules(rules.map((x, j) => (j === i ? { ...x, days: Number(e.target.value) } : x)))
            }
          />
          <Field
            label={t('Gebühr in Prozent')}
            type="number"
            min={0}
            max={100}
            value={rule.percent}
            onChange={(e) =>
              setRules(
                rules.map((x, j) => (j === i ? { ...x, percent: Number(e.target.value) } : x)),
              )
            }
          />
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setRules(rules.filter((_, j) => j !== i))}
          >
            {t('Stufe entfernen')}
          </button>
        </div>
      ))}
      <div className="button-row">
        {rules.length < 6 && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setRules([...rules, { days: 0, percent: 50 }])}
          >
            <span aria-hidden="true">+</span> {t('Stufe für Stornogebühr')}
          </button>
        )}
      </div>
      <div className="form-grid">
        <Field
          label={t('Bearbeitungsgebühr bei Abmeldung in € (optional)')}
          inputMode="decimal"
          hint={t('kommt dazu, sobald eine Stufe greift; ohne Stufen bei jeder Abmeldung')}
          value={v.cancel_fee_fixed}
          onChange={(e) => setV({ ...v, cancel_fee_fixed: e.target.value })}
        />
        <Field
          label={t('Unbezahlte Anmeldungen verfallen … Tage vor Beginn (optional)')}
          type="number"
          min={1}
          max={90}
          hint={t('leer: nie; der Platz geht dann an die Warteliste')}
          value={v.expire_unpaid_days}
          onChange={(e) => setV({ ...v, expire_unpaid_days: e.target.value })}
        />
      </div>
      <h4>{t('Tarife')}</h4>
      {prices.map((p, i) => (
        <fieldset key={i} className="card stack-sm">
          <legend>{p.name || t('Tarif {n}', { n: i + 1 })}</legend>
          <div className="form-grid">
            <Field
              label={t('Name')}
              value={p.name}
              maxLength={100}
              onChange={(e) => setPrice(i, { name: e.target.value })}
            />
            <Field
              label={t('Name auf Englisch (optional)')}
              value={p.name_en ?? ''}
              maxLength={100}
              onChange={(e) => setPrice(i, { name_en: e.target.value })}
            />
            <SelectField
              label={t('Gilt für')}
              value={p.applies}
              onChange={(e) => setPrice(i, { applies: e.target.value as PriceInput['applies'] })}
            >
              <option value="all">{t('alle')}</option>
              <option value="members">{t('nur Mitglieder')}</option>
              <option value="guests">{t('nur Gäste')}</option>
            </SelectField>
            <Field
              label={t('Alter von')}
              type="number"
              min={0}
              value={p.age_from ?? ''}
              onChange={(e) => setPrice(i, { age_from: num(e.target.value) })}
            />
            <Field
              label={t('Alter bis')}
              type="number"
              min={0}
              value={p.age_to ?? ''}
              onChange={(e) => setPrice(i, { age_to: num(e.target.value) })}
            />
            <Field
              label={t('Plätze in diesem Tarif (optional)')}
              type="number"
              min={1}
              value={p.capacity ?? ''}
              onChange={(e) => setPrice(i, { capacity: num(e.target.value) })}
            />
            <SelectField
              label={t('Umsatzsteuer im Preis')}
              value={p.vat_rate ? String(Number(p.vat_rate)) : ''}
              onChange={(e) => setPrice(i, { vat_rate: e.target.value || null })}
            >
              <option value="">{t('keine')}</option>
              <option value="7">7 %</option>
              <option value="19">19 %</option>
            </SelectField>
          </div>
          <p className="muted small">
            {t(
              'Preisstufen gelten nacheinander, z. B. Early Bird bis zu einem Datum oder für die ersten Plätze. Die letzte Stufe gilt bis zum Anmeldeschluss.',
            )}
          </p>
          {p.steps.map((s, k) => {
            const last = k === p.steps.length - 1
            return (
              <div key={k} className="form-grid">
                <Field
                  label={t('Stufe {n}: Name (optional)', { n: k + 1 })}
                  value={s.name}
                  maxLength={60}
                  placeholder={k === 0 && p.steps.length > 1 ? t('Early Bird') : ''}
                  onChange={(e) => setStep(i, k, { name: e.target.value })}
                />
                <Field
                  label={t('Betrag in €')}
                  inputMode="decimal"
                  value={s.amount}
                  onChange={(e) => setStep(i, k, { amount: e.target.value })}
                />
                {!last && (
                  <>
                    <Field
                      label={t('gilt bis (Datum)')}
                      type="date"
                      value={s.until_date ?? ''}
                      onChange={(e) => setStep(i, k, { until_date: e.target.value || null })}
                    />
                    <Field
                      label={t('für die ersten … Personen')}
                      type="number"
                      min={1}
                      value={s.until_count ?? ''}
                      onChange={(e) => setStep(i, k, { until_count: num(e.target.value) })}
                    />
                  </>
                )}
                {p.steps.length > 1 && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setPrice(i, { steps: p.steps.filter((_, j) => j !== k) })}
                  >
                    {t('Stufe entfernen')}
                  </button>
                )}
              </div>
            )
          })}
          <div className="button-row">
            {p.steps.length < 6 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  setPrice(i, {
                    steps: [
                      { name: '', amount: '', until_date: null, until_count: null },
                      ...p.steps,
                    ],
                  })
                }
              >
                <span aria-hidden="true">+</span> {t('Frühere Preisstufe')}
              </button>
            )}
            {prices.length > 1 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setPrices(prices.filter((_, j) => j !== i))}
              >
                {t('Tarif entfernen')}
              </button>
            )}
          </div>
        </fieldset>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => setPrices([...prices, emptyPrice()])}
        >
          <span aria-hidden="true">+</span> {t('Tarif hinzufügen')}
        </button>
      </div>
      <h4>{t('Öffentliche Anmeldung')}</h4>
      <Checkbox
        label={t('Auch Nichtmitglieder können sich anmelden (Formular mit Link)')}
        hint={
          event.visibility === 'public'
            ? t(
                'Wer sich so anmeldet, bestätigt die E-Mail-Adresse; erst dann gilt die Anmeldung und die Rechnung kommt. Den Link zum Formular siehst du nach dem Speichern.',
              )
            : t('Nur bei Terminen mit der Sichtbarkeit „öffentlich“.')
        }
        checked={v.public && event.visibility === 'public'}
        disabled={event.visibility !== 'public'}
        onChange={(on) => setV({ ...v, public: on })}
      />
      {data.club_registration_possible && (
        <>
          <h4>{t('Sammelanmeldung')}</h4>
          <Checkbox
            label={t('Vereine melden ihre Mitglieder gesammelt an')}
            hint={t(
              'Die Vereine sehen den Termin in ihrem Kalender und melden dort Mitglieder an. Die Rechnung geht an den Verein. Die Vereine brauchen dafür das Modul Anmeldungen.',
            )}
            checked={v.club_registration}
            onChange={(on) => setV({ ...v, club_registration: on })}
          />
        </>
      )}
      <h4>{t('Zusatzleistungen und Fragen')}</h4>
      <Checkbox
        label={t('mit Verpflegung')}
        hint={t('Nur dann darf nach Allergien und Unverträglichkeiten gefragt werden.')}
        checked={v.catering}
        onChange={(on) => setV({ ...v, catering: on })}
      />
      <Checkbox
        label={t('Minderjährige möglich')}
        hint={t(
          'Fragt immer das Geburtsdatum ab; unter 18 sind Name, Telefon und E-Mail einer oder eines Erziehungsberechtigten Pflicht.',
        )}
        checked={v.minors}
        onChange={(on) => setV({ ...v, minors: on })}
      />
      <AddOnsEditor addons={addons} onChange={setAddons} canSetPrices={data.can_set_prices} />
      <QuestionsEditor
        questions={questions}
        onChange={setQuestions}
        healthAllowed={healthAllowed}
      />
      {dropsHealth && (
        <Alert kind="info">
          {t(
            'Ohne Verpflegung fällt die Frage nach Allergien weg; schon erfasste Angaben werden beim Speichern gelöscht.',
          )}
        </Alert>
      )}
      <div className="button-row">
        <button type="button" className="button" disabled={busy} onClick={() => void save()}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
        {offer && data.registrations.length === 0 && (
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Anmeldung entfernen')}
          </button>
        )}
      </div>
    </div>
  )
}
