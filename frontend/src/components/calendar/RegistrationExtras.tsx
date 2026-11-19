// Zusatzleistungen, Zusatzfragen, Gesundheitsangaben und Erziehungsberechtigte bei der Anmeldung
// (konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A5, F11, F13).
import type {
  AddOn,
  AddOnInput,
  Answer,
  Guardian,
  Offer,
  Per,
  QuestionInput,
} from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import { Checkbox, Field, SelectField } from '../ui.tsx'
import { t } from '../../i18n/index.ts'
import { activeAddons, activeQuestions, name, question } from './extras.ts'
import type { ExtrasState } from './extras.ts'

function choiceLabel(c: AddOn['choices'][number]): string {
  const price = Number(c.amount) > 0 ? ` (+${euro(c.amount)})` : ''
  const full = c.free === 0 ? ` – ${t('ausgebucht')}` : ''
  return `${name(c)}${price}${full}`
}

export function ExtrasFields({
  offer,
  per,
  state,
  onChange,
  who,
  minor = false,
}: {
  offer: Offer
  per: Per
  state: ExtrasState
  onChange: (next: ExtrasState) => void
  /** Name der Person, für die Beschriftung */
  who?: string
  minor?: boolean
}) {
  const addons = activeAddons(offer, per)
  const questions = activeQuestions(offer, per)
  if (!addons.length && !questions.length && !minor) return null
  const suffix = who ? ` (${who})` : ''
  const setAddon = (id: number, value: number | null) =>
    onChange({ ...state, addons: { ...state.addons, [String(id)]: value } })
  const setAnswer = (id: number, value: Answer) =>
    onChange({ ...state, answers: { ...state.answers, [String(id)]: value } })
  const guardian = (i: number): Guardian =>
    state.guardians[i] ?? { name: '', phone: '', email: '', address: '' }
  const setGuardian = (i: number, patch: Partial<Guardian>) => {
    const rows = [guardian(0), guardian(1)]
    rows[i] = { ...rows[i], ...patch }
    onChange({ ...state, guardians: rows })
  }
  return (
    <div className="stack-sm">
      {addons.map((a) => (
        <SelectField
          key={a.id}
          label={`${name(a)}${suffix}`}
          value={String(state.addons[String(a.id)] ?? '')}
          onChange={(e) => setAddon(a.id, e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{a.required ? t('bitte wählen …') : t('nicht gewünscht')}</option>
          {a.choices
            .filter((c) => c.is_active)
            .map((c) => (
              <option
                key={c.id}
                value={c.id}
                disabled={c.free === 0 && state.addons[String(a.id)] !== c.id}
              >
                {choiceLabel(c)}
              </option>
            ))}
        </SelectField>
      ))}
      {questions.map((q) => {
        const label = `${question(q)}${suffix}${q.required ? '' : ` ${t('(optional)')}`}`
        const value = state.answers[String(q.id)]
        if (q.kind === 'health')
          return (
            <Field
              key={q.id}
              label={`${question(q)}${suffix} ${t('(optional)')}`}
              hint={t(
                'Nur für die Planung des Essens; sieht nur die Verwaltung, wird 14 Tage nach der Veranstaltung gelöscht.',
              )}
              value={state.health}
              maxLength={500}
              onChange={(e) => onChange({ ...state, health: e.target.value })}
            />
          )
        if (q.kind === 'yesno')
          return (
            <SelectField
              key={q.id}
              label={label}
              value={value === true ? 'yes' : value === false ? 'no' : ''}
              onChange={(e) =>
                setAnswer(q.id, e.target.value === '' ? '' : e.target.value === 'yes')
              }
            >
              <option value="">{t('bitte wählen …')}</option>
              <option value="yes">{t('ja')}</option>
              <option value="no">{t('nein')}</option>
            </SelectField>
          )
        if (q.kind === 'choice')
          return (
            <SelectField
              key={q.id}
              label={label}
              value={typeof value === 'string' ? value : ''}
              onChange={(e) => setAnswer(q.id, e.target.value)}
            >
              <option value="">{t('bitte wählen …')}</option>
              {q.choices.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </SelectField>
          )
        return (
          <Field
            key={q.id}
            label={label}
            value={typeof value === 'string' ? value : ''}
            maxLength={500}
            onChange={(e) => setAnswer(q.id, e.target.value)}
          />
        )
      })}
      {minor && (
        <fieldset className="stack-sm">
          <legend>{t('Erziehungsberechtigte{who}', { who: suffix })}</legend>
          <p className="muted small">
            {t(
              'Unter 18: Bitte Name, Telefon (während der Veranstaltung erreichbar) und E-Mail angeben; die Anschrift nur, wenn sie abweicht.',
            )}
          </p>
          {[0, 1].map((i) => (
            <div key={i} className="grid-2">
              <Field
                label={i === 0 ? t('Name') : t('Zweite Person (optional)')}
                value={guardian(i).name}
                maxLength={200}
                onChange={(e) => setGuardian(i, { name: e.target.value })}
              />
              <Field
                label={t('Telefon')}
                type="tel"
                value={guardian(i).phone}
                maxLength={50}
                onChange={(e) => setGuardian(i, { phone: e.target.value })}
              />
              <Field
                label={t('E-Mail')}
                type="email"
                value={guardian(i).email}
                maxLength={254}
                onChange={(e) => setGuardian(i, { email: e.target.value })}
              />
              <Field
                label={t('Anschrift (optional)')}
                value={guardian(i).address ?? ''}
                maxLength={1000}
                onChange={(e) => setGuardian(i, { address: e.target.value })}
              />
            </div>
          ))}
        </fieldset>
      )}
    </div>
  )
}

export function HealthConsent({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (on: boolean) => void
}) {
  return (
    <Checkbox
      label={t(
        'Ich willige ein, dass der Verein die Angaben zu Allergien und Unverträglichkeiten für die Planung des Essens verarbeitet.',
      )}
      checked={checked}
      onChange={onChange}
    />
  )
}

// --- Einrichten (Verwaltung) ---

const numOrNull = (v: string) => (v.trim() === '' ? null : Number(v))

export function AddOnsEditor({
  addons,
  onChange,
  canSetPrices,
}: {
  addons: AddOnInput[]
  onChange: (next: AddOnInput[]) => void
  canSetPrices: boolean
}) {
  const set = (i: number, patch: Partial<AddOnInput>) =>
    onChange(addons.map((a, j) => (j === i ? { ...a, ...patch } : a)))
  return (
    <fieldset className="stack-sm">
      <legend>{t('Zusatzleistungen')}</legend>
      <p className="muted small">
        {t(
          'Wählbar je Person oder je Anmeldung, mit Aufpreis (auch 0 €) und Platzgrenze, z. B. Busfahrt oder Menü. Erscheint als eigener Posten auf der Rechnung und als Spalte in der Teilnehmerliste.',
        )}
      </p>
      {addons.map((a, i) => (
        <div key={a.id ?? `neu-${i}`} className="card stack-sm">
          <div className="grid-2">
            <Field
              label={t('Name')}
              value={a.name}
              maxLength={100}
              onChange={(e) => set(i, { name: e.target.value })}
            />
            <Field
              label={t('Name (Englisch, optional)')}
              value={a.name_en}
              maxLength={100}
              onChange={(e) => set(i, { name_en: e.target.value })}
            />
            <SelectField
              label={t('Art')}
              value={a.kind}
              onChange={(e) => set(i, { kind: e.target.value as AddOnInput['kind'] })}
            >
              <option value="other">{t('sonstiges')}</option>
              <option value="meal">{t('Essen')}</option>
            </SelectField>
            <SelectField
              label={t('Gilt')}
              value={a.per}
              onChange={(e) => set(i, { per: e.target.value as Per })}
            >
              <option value="person">{t('je Person')}</option>
              <option value="registration">{t('je Anmeldung')}</option>
            </SelectField>
          </div>
          <Checkbox
            label={t('Pflicht (eine Auswahl muss getroffen werden)')}
            checked={a.required}
            onChange={(on) => set(i, { required: on })}
          />
          {a.choices.map((c, k) => (
            <div key={c.id ?? `neu-${k}`} className="grid-2">
              <Field
                label={t('Auswahl')}
                value={c.name}
                maxLength={100}
                onChange={(e) =>
                  set(i, {
                    choices: a.choices.map((x, m) =>
                      m === k ? { ...x, name: e.target.value } : x,
                    ),
                  })
                }
              />
              <Field
                label={t('Aufpreis in €')}
                inputMode="decimal"
                value={c.amount}
                disabled={!canSetPrices}
                onChange={(e) =>
                  set(i, {
                    choices: a.choices.map((x, m) =>
                      m === k ? { ...x, amount: e.target.value } : x,
                    ),
                  })
                }
              />
              <Field
                label={t('Plätze (optional)')}
                type="number"
                min={1}
                value={c.capacity ?? ''}
                onChange={(e) =>
                  set(i, {
                    choices: a.choices.map((x, m) =>
                      m === k ? { ...x, capacity: numOrNull(e.target.value) } : x,
                    ),
                  })
                }
              />
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost small"
                  disabled={a.choices.length < 2}
                  onClick={() => set(i, { choices: a.choices.filter((_, m) => m !== k) })}
                >
                  {t('Auswahl entfernen')}
                </button>
              </div>
            </div>
          ))}
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost small"
              onClick={() =>
                set(i, {
                  choices: [
                    ...a.choices,
                    {
                      name: '',
                      name_en: '',
                      amount: '0',
                      vat_rate: null,
                      capacity: null,
                      is_active: true,
                    },
                  ],
                })
              }
            >
              <span aria-hidden="true">+</span> {t('Auswahl hinzufügen')}
            </button>
            <button
              type="button"
              className="button button-ghost small"
              onClick={() => onChange(addons.filter((_, j) => j !== i))}
            >
              {t('Zusatzleistung entfernen')}
            </button>
          </div>
        </div>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            onChange([
              ...addons,
              {
                name: '',
                name_en: '',
                kind: 'other',
                per: 'person',
                required: false,
                is_active: true,
                choices: [
                  {
                    name: '',
                    name_en: '',
                    amount: '0',
                    vat_rate: null,
                    capacity: null,
                    is_active: true,
                  },
                ],
              },
            ])
          }
        >
          <span aria-hidden="true">+</span> {t('Zusatzleistung hinzufügen')}
        </button>
      </div>
    </fieldset>
  )
}

export function QuestionsEditor({
  questions,
  onChange,
  healthAllowed,
}: {
  questions: QuestionInput[]
  onChange: (next: QuestionInput[]) => void
  healthAllowed: boolean
}) {
  const set = (i: number, patch: Partial<QuestionInput>) =>
    onChange(questions.map((q, j) => (j === i ? { ...q, ...patch } : q)))
  const hasHealth = questions.some((q) => q.kind === 'health')
  return (
    <fieldset className="stack-sm">
      <legend>{t('Zusatzfragen')}</legend>
      <p className="muted small">
        {t(
          'Fragen ohne Preis, z. B. Tischwunsch oder Telefon für Rückfragen am Tag. Nach Allergien und Unverträglichkeiten darf nur gefragt werden, wenn es Essen gibt.',
        )}
      </p>
      {questions.map((q, i) => (
        <div key={q.id ?? `neu-${i}`} className="card stack-sm">
          <div className="grid-2">
            <Field
              label={t('Frage')}
              value={q.text}
              maxLength={200}
              onChange={(e) => set(i, { text: e.target.value })}
            />
            <Field
              label={t('Frage (Englisch, optional)')}
              value={q.text_en}
              maxLength={200}
              onChange={(e) => set(i, { text_en: e.target.value })}
            />
            <SelectField
              label={t('Art')}
              value={q.kind}
              onChange={(e) => set(i, { kind: e.target.value as QuestionInput['kind'] })}
            >
              <option value="text">{t('Text')}</option>
              <option value="yesno">{t('Ja/Nein')}</option>
              <option value="choice">{t('Auswahl')}</option>
              {(healthAllowed || q.kind === 'health') && (
                <option value="health" disabled={hasHealth && q.kind !== 'health'}>
                  {t('Allergien und Unverträglichkeiten')}
                </option>
              )}
            </SelectField>
            {q.kind !== 'health' && (
              <SelectField
                label={t('Gilt')}
                value={q.per}
                onChange={(e) => set(i, { per: e.target.value as Per })}
              >
                <option value="registration">{t('je Anmeldung')}</option>
                <option value="person">{t('je Person')}</option>
              </SelectField>
            )}
          </div>
          {q.kind === 'choice' && (
            <Field
              label={t('Antworten, mit Komma getrennt')}
              value={q.choices.join(', ')}
              onChange={(e) =>
                set(i, { choices: e.target.value.split(',').map((x) => x.trimStart()) })
              }
            />
          )}
          {q.kind === 'health' ? (
            <p className="muted small">
              {t(
                'Freiwillig und nur mit Einwilligung. Die Angaben sieht nur die Verwaltung, sie werden 14 Tage nach der Veranstaltung gelöscht.',
              )}
            </p>
          ) : (
            <Checkbox
              label={t('Pflichtfrage')}
              checked={q.required}
              onChange={(on) => set(i, { required: on })}
            />
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost small"
              onClick={() => onChange(questions.filter((_, j) => j !== i))}
            >
              {t('Frage entfernen')}
            </button>
          </div>
        </div>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            onChange([
              ...questions,
              {
                text: '',
                text_en: '',
                kind: 'text',
                choices: [],
                required: false,
                per: 'registration',
                is_active: true,
              },
            ])
          }
        >
          <span aria-hidden="true">+</span> {t('Frage hinzufügen')}
        </button>
      </div>
    </fieldset>
  )
}
