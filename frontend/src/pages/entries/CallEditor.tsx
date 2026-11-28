// Meldungen: Ausschreibung bearbeiten (Angaben, Bedingungen, Blöcke).
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BLOCK_LABELS,
  entriesApi,
  type BlockKind,
  type BlockSettings,
  type Call,
  type CallBlock,
  type CallDetail,
  type Conditions,
  type EntryOptions,
} from '../../api/entries.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { CallEventCard } from './CallEvent.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'

function numOrNull(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

export function CallEditor({
  org,
  call,
  options,
  onChanged,
  reload,
}: {
  org: number
  call: CallDetail
  options: EntryOptions
  onChanged: (c: CallDetail) => void
  reload: () => void
}) {
  const navigate = useNavigate()
  const form = useForm({
    title: call.title,
    organizer: call.organizer,
    organizer_address: call.organizer_address,
    organizer_email: call.organizer_email,
    salutation: call.salutation,
    description: call.description,
    date: call.date ?? '',
    location: call.location,
    deadline: call.deadline ?? '',
    reference_date: call.reference_date ?? '',
    person_fields: call.person_fields,
    conditions: call.conditions,
    fee_amount: call.fee_amount ?? '',
    fee_per: call.fee_per,
    changes_after_deadline: call.changes_after_deadline,
    create_competition: call.create_competition,
    units: call.units,
    strict: call.strict,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(
    form,
    (changes) => {
      const data: Record<string, unknown> = { ...changes }
      for (const k of ['date', 'deadline', 'reference_date', 'fee_amount'] as const)
        if (k in data && data[k] === '') data[k] = null
      return entriesApi.update(org, call.id, data as Partial<Call>)
    },
    { onSaved: (saved) => onChanged(saved as CallDetail) },
  )
  const cond = v.conditions
  const setCond = (c: Partial<Conditions>) => set('conditions', { ...cond, ...c })
  const toggle = (list: number[] | undefined, id: number, on: boolean) =>
    on ? [...(list ?? []), id] : (list ?? []).filter((x) => x !== id)

  async function copy() {
    const created = await entriesApi.copy(org, call.id)
    navigate(`/meldungen/${created.id}/ausschreibung`)
  }

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Ausschreibung löschen'),
      message: t('„{x1}“ samt Entwurf löschen?', { x1: call.title }),
      confirmLabel: t('Löschen'),
      danger: true,
    })
    if (!ok) return
    try {
      await entriesApi.remove(org, call.id)
      navigate('/meldungen')
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <>
      <div className="card card-wide">
        <div className="card-head">
          <h2>{t('Ausschreibung')}</h2>
          <SaveStatus auto={auto} />
        </div>
        <div className="grid-3">
          <Field
            label={t('Titel')}
            value={v.title}
            error={errors.title}
            onChange={(e) => set('title', e.target.value)}
          />
          <Field
            label={t('Datum des Anlasses')}
            type="date"
            value={v.date}
            error={errors.date}
            onChange={(e) => set('date', e.target.value)}
          />
          <Field
            label={t('Ort')}
            value={v.location}
            error={errors.location}
            onChange={(e) => set('location', e.target.value)}
          />
          <Field
            label={t('Meldeschluss')}
            type="date"
            value={v.deadline}
            error={errors.deadline}
            onChange={(e) => set('deadline', e.target.value)}
          />
          <SelectField
            label={t('Nach Meldeschluss')}
            value={v.changes_after_deadline}
            onChange={(e) =>
              set('changes_after_deadline', e.target.value as Call['changes_after_deadline'])
            }
          >
            <option value="ersatz">{t('nur Ersatz von Personen')}</option>
            <option value="keine">{t('keine Änderungen')}</option>
            <option value="frei">{t('Änderungen bis zum Anlass')}</option>
          </SelectField>
          <Field
            label={t('Stichtag für Alter und Mitgliedschaft')}
            type="date"
            hint={t('leer: Datum des Anlasses')}
            value={v.reference_date}
            error={errors.reference_date}
            onChange={(e) => set('reference_date', e.target.value)}
          />
        </div>
        {call.internal && (
          <fieldset>
            <legend>
              {t('Angeschriebene ')}
              {options.unit_label}
              {t('-Einheiten (keine Auswahl: alle direkt darunter)')}
            </legend>
            {options.units.map((u) => (
              <Checkbox
                key={u.id}
                label={u.name}
                checked={v.units.includes(u.id)}
                onChange={(on) => set('units', toggle(v.units, u.id, on))}
              />
            ))}
          </fieldset>
        )}
        {!call.internal && <h3>{t('Veranstalter')}</h3>}
        {!call.internal && (
          <div className="grid-3">
            <Field
              label={t('Name')}
              value={v.organizer}
              error={errors.organizer}
              onChange={(e) => set('organizer', e.target.value)}
            />
            <label className="field">
              <span>{t('Anschrift (ohne Name)')}</span>
              <textarea
                rows={3}
                value={v.organizer_address}
                onChange={(e) => set('organizer_address', e.target.value)}
              />
            </label>
            <Field
              label={t('E-Mail')}
              type="email"
              value={v.organizer_email}
              error={errors.organizer_email}
              onChange={(e) => set('organizer_email', e.target.value)}
            />
            <Field
              label={t('Anrede im Brief')}
              value={v.salutation}
              error={errors.salutation}
              onChange={(e) => set('salutation', e.target.value)}
            />
          </div>
        )}
        <label className="field">
          <span>{t('Beschreibung (z. B. Auszug aus der Ausschreibung)')}</span>
          <textarea
            rows={3}
            value={v.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </label>
        <h3>{t('Meldegebühr')}</h3>
        <div className="grid-3">
          <Field
            label={t('Betrag (€)')}
            inputMode="decimal"
            value={v.fee_amount}
            error={errors.fee_amount}
            onChange={(e) => set('fee_amount', e.target.value)}
          />
          <SelectField
            label={t('berechnet')}
            value={v.fee_per}
            onChange={(e) => set('fee_per', e.target.value as Call['fee_per'])}
          >
            <option value="mannschaft">{t('je Mannschaft')}</option>
            <option value="person">{t('je Person')}</option>
            <option value="pauschal">{t('pauschal')}</option>
          </SelectField>
        </div>
        <h3>{t('Angaben je Person')}</h3>
        <Why k="entry_person_fields" />
        <p className="muted small">
          {t('Nur angekreuzte Angaben gehen an den Veranstalter. Der Name steht immer drin.')}
        </p>
        <div className="grid-3">
          {options.person_fields.map((f) => (
            <Checkbox
              key={f.key}
              label={f.label}
              checked={v.person_fields.includes(f.key)}
              onChange={(on) =>
                set(
                  'person_fields',
                  on ? [...v.person_fields, f.key] : v.person_fields.filter((k) => k !== f.key),
                )
              }
            />
          ))}
        </div>
        <h3>{t('Bedingungen')}</h3>
        <p className="muted small">
          {t(
            'HUBIplan weist auf Verstöße hin; abgeben bleibt möglich, der Veranstalter entscheidet.',
          )}
        </p>
        {call.internal && (
          <Checkbox
            label={t('Verstöße sperren das Abgeben')}
            hint={t('sonst nur Hinweise; ihr entscheidet beim Bestätigen')}
            checked={v.strict}
            onChange={(on) => set('strict', on)}
          />
        )}
        <div className="grid-3">
          <Checkbox
            label={t('nur aktive Mitglieder am Stichtag')}
            checked={!!cond.active}
            onChange={(on) => setCond({ active: on })}
          />
          <Checkbox
            label={t('Gäste (Nichtmitglieder) erlaubt')}
            checked={!!cond.guests}
            onChange={(on) => setCond({ guests: on })}
          />
          <Checkbox
            label={t('jede Person nur in einer Mannschaft')}
            checked={!!cond.one_team}
            onChange={(on) => setCond({ one_team: on })}
          />
          <Field
            label={t('Mindestalter')}
            type="number"
            min={0}
            value={cond.min_age ?? ''}
            error={errors.min_age}
            onChange={(e) => setCond({ min_age: numOrNull(e.target.value) ?? undefined })}
          />
          <Field
            label={t('Höchstalter')}
            type="number"
            min={0}
            value={cond.max_age ?? ''}
            error={errors.max_age}
            onChange={(e) => setCond({ max_age: numOrNull(e.target.value) ?? undefined })}
          />
        </div>
        {options.member_types.length > 0 && (
          <fieldset>
            <legend>{t('nur diese Mitgliedsarten (keine Auswahl: alle)')}</legend>
            {options.member_types.map((t) => (
              <Checkbox
                key={t.id}
                label={t.name}
                checked={(cond.member_types ?? []).includes(t.id)}
                onChange={(on) => setCond({ member_types: toggle(cond.member_types, t.id, on) })}
              />
            ))}
          </fieldset>
        )}
        {options.units.length > 0 && (
          <fieldset>
            <legend>
              {t('nur aus diesen ')}
              {options.unit_label}
              {t('-Einheiten (keine Auswahl: alle)')}
            </legend>
            {options.units.map((u) => (
              <Checkbox
                key={u.id}
                label={u.name}
                checked={(cond.units ?? []).includes(u.id)}
                onChange={(on) => setCond({ units: toggle(cond.units, u.id, on) })}
              />
            ))}
          </fieldset>
        )}
        {options.competitions_enabled && (
          <Checkbox
            label={
              call.internal
                ? t('bestätigte Meldungen als Starter in einen eigenen Wettbewerb übernehmen')
                : t('beim Abgeben einen fremden Wettbewerb mit den Mannschaften anlegen')
            }
            hint={
              call.internal
                ? t(
                    'der Wettbewerb entsteht beim ersten Bestätigen, mit Wertung der Untereinheiten',
                  )
                : t('dort tragt ihr später eure Plätze ein')
            }
            checked={v.create_competition}
            onChange={(on) => set('create_competition', on)}
          />
        )}
        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={copy}>
            {t('Für das nächste Jahr kopieren')}
          </button>
          {!call.has_versions && (
            <button type="button" className="button button-ghost" onClick={remove}>
              {t('Ausschreibung löschen')}
            </button>
          )}
        </div>
      </div>
      <CallEventCard org={org} call={call} onChanged={onChanged} />
      <BlocksEditor org={org} call={call} reload={reload} />
    </>
  )
}

function BlocksEditor({
  org,
  call,
  reload,
}: {
  org: number
  call: CallDetail
  reload: () => void
}) {
  const [kind, setKind] = useState<BlockKind>('mannschaften')
  const [message, setMessage] = useState<string | null>(null)
  async function add() {
    setMessage(null)
    try {
      await entriesApi.addBlock(org, call.id, {
        kind,
        label: BLOCK_LABELS[kind],
        settings: kind === 'auswahl' ? { options: ['ja', 'nein'] } : {},
      })
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }
  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Was gemeldet wird')}</h2>
      </div>
      <p className="muted">
        {t(
          'Bausteine des Meldeformulars: Mannschaften, eine Personenliste (z. B. Delegierte), eine Zahl (z. B. Teilnehmer am Ausflug), eine Auswahl oder ein Text.',
        )}
      </p>
      {call.blocks.map((b) => (
        <BlockCard key={b.id} org={org} call={call} block={b} reload={reload} />
      ))}
      {message && <Alert kind="error">{message}</Alert>}
      <div className="grid-3">
        <SelectField
          label={t('Baustein')}
          value={kind}
          onChange={(e) => setKind(e.target.value as BlockKind)}
        >
          {(Object.keys(BLOCK_LABELS) as BlockKind[]).map((k) => (
            <option key={k} value={k}>
              {BLOCK_LABELS[k]}
            </option>
          ))}
        </SelectField>
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={add}>
            {t('Baustein hinzufügen')}
          </button>
        </div>
      </div>
    </div>
  )
}

function BlockCard({
  org,
  call,
  block,
  reload,
}: {
  org: number
  call: CallDetail
  block: CallBlock
  reload: () => void
}) {
  const form = useForm({
    label: block.label,
    help_text: block.help_text,
    required: block.required,
    settings: block.settings,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(form, (changes) =>
    entriesApi.updateBlock(org, call.id, block.id, changes),
  )
  const s = v.settings
  const setS = (x: Partial<BlockSettings>) => set('settings', { ...s, ...x })
  const num = (key: keyof BlockSettings, label: string) => (
    <Field
      label={label}
      type="number"
      min={0}
      value={(s[key] as number | undefined) ?? ''}
      error={errors[key]}
      onChange={(e) => setS({ [key]: numOrNull(e.target.value) ?? undefined })}
    />
  )
  const list = (key: 'positions' | 'options', label: string, hint: string) => (
    <Field
      label={label}
      hint={hint}
      value={(s[key] ?? []).join(', ')}
      error={errors[key]}
      onChange={(e) =>
        setS({
          [key]: e.target.value
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean),
        })
      }
    />
  )

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Baustein entfernen'),
      message: t('„{x1}“ samt den Einträgen der Meldung entfernen?', { x1: block.label }),
      confirmLabel: t('Entfernen'),
      danger: true,
    })
    if (!ok) return
    try {
      await entriesApi.removeBlock(org, call.id, block.id)
      reload()
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h3>{BLOCK_LABELS[block.kind]}</h3>
        <SaveStatus auto={auto} />
        <button type="button" className="button button-ghost push-right" onClick={remove}>
          {t('Entfernen')}
        </button>
      </div>
      <div className="grid-3">
        <Field
          label={t('Bezeichnung')}
          value={v.label}
          error={errors.label}
          onChange={(e) => set('label', e.target.value)}
        />
        <Field
          label={t('Hinweis')}
          value={v.help_text}
          error={errors.help_text}
          onChange={(e) => set('help_text', e.target.value)}
        />
        <Checkbox
          label={t('Pflicht')}
          checked={v.required}
          onChange={(on) => set('required', on)}
        />
        {block.kind === 'mannschaften' && (
          <>
            {num('min_teams', t('Mannschaften mindestens'))}
            {num('max_teams', t('Mannschaften höchstens'))}
            {num('min_size', t('Personen je Mannschaft mindestens'))}
            {num('max_size', t('Personen je Mannschaft höchstens'))}
            {num('substitutes', t('Ersatzleute je Mannschaft höchstens'))}
            {list('positions', t('Aufgaben'), t('z. B. Mannschaftsführer, mit Komma getrennt'))}
          </>
        )}
        {block.kind === 'personen' && (
          <>
            {num('min', t('Personen mindestens'))}
            {num('max', t('Personen höchstens'))}
            {list('positions', t('Aufgaben'), t('z. B. Delegierter, Betreuer'))}
          </>
        )}
        {block.kind === 'zahl' && (
          <>
            {num('min', t('kleinster Wert'))}
            {num('max', t('größter Wert'))}
          </>
        )}
        {block.kind === 'auswahl' && (
          <>
            {list('options', t('Antworten'), t('mit Komma getrennt'))}
            <Checkbox
              label={t('mehrere Antworten möglich')}
              checked={!!s.multiple}
              onChange={(on) => setS({ multiple: on })}
            />
          </>
        )}
        {block.kind === 'text' && (
          <Checkbox
            label={t('mehrzeilig')}
            checked={!!s.multiline}
            onChange={(on) => setS({ multiline: on })}
          />
        )}
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
    </div>
  )
}
