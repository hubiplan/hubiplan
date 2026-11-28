import { useState } from 'react'
import type { FormEvent } from 'react'
import { surveyApi } from '../../api/surveys.ts'
import type {
  Audience,
  NamesMode,
  ResultsMode,
  Survey,
  SurveyChoices,
  SurveyMember,
  SurveyQuestion,
} from '../../api/surveys.ts'
import { berlin } from '../../components/calendar/time.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import { dateLabel } from './SurveyParts.tsx'
import './surveys.css'
import { Why } from '../../learning/Aids.tsx'
import {
  emptyOption,
  emptyQuestion,
  local,
  namesLabel,
  resultsLabel,
  toApiTime,
} from './surveysHelpers.ts'
import { QuestionEditor } from './QuestionEditor.tsx'

/** Anonyme Umfragen zeigen ihr Ergebnis erst nach dem Ende (Gesamtaudit 15.11., FF-22). */
const ANONYMOUS_RESULTS: ResultsMode[] = ['after_close', 'managers']

type Template = 'dates' | 'meal' | 'ride' | 'opinion' | 'free'

function templateLabel(tpl: Template) {
  switch (tpl) {
    case 'dates':
      return t('Termin finden')
    case 'meal':
      return t('Essenswahl')
    case 'ride':
      return t('Wer fährt mit?')
    case 'opinion':
      return t('Meinungsbild (Ja/Nein/Enthaltung)')
    default:
      return t('Freie Umfrage')
  }
}

function fromTemplate(tpl: Template): { questions: SurveyQuestion[]; names: NamesMode } {
  switch (tpl) {
    case 'dates':
      return {
        questions: [{ ...emptyQuestion('dates'), text: t('Welche Termine passen dir?') }],
        names: 'open',
      }
    case 'meal':
      return {
        questions: [
          {
            ...emptyQuestion('quantity'),
            text: t('Was möchtest du essen?'),
            options: [emptyOption(), emptyOption(), emptyOption()],
          },
        ],
        names: 'open',
      }
    case 'ride':
      return {
        questions: [
          {
            ...emptyQuestion('single'),
            text: t('Wie fährst du mit?'),
            options: [
              { ...emptyOption(), label: t('Bus'), capacity: 50 },
              { ...emptyOption(), label: t('eigenes Auto') },
              { ...emptyOption(), label: t('fahre nicht mit') },
            ],
          },
        ],
        names: 'open',
      }
    case 'opinion':
      return { questions: [{ ...emptyQuestion('yesno') }], names: 'managers' }
    default:
      return { questions: [emptyQuestion('single')], names: 'managers' }
  }
}

interface Form {
  title: string
  description: string
  event: number | null
  audience: Audience
  departments: number[]
  member_types: number[]
  board: boolean
  persons: SurveyMember[]
  names: NamesMode
  results: ResultsMode
  closes_at: string
  remind_days: string
  keep_months: string
  questions: SurveyQuestion[]
}

function defaultEnd() {
  const d = new Date(Date.now() + 7 * 86400000)
  return `${berlin(d.toISOString()).date}T20:00`
}

function toForm(s: Survey | null): Form {
  if (!s) {
    return {
      title: '',
      description: '',
      event: null,
      audience: 'members',
      departments: [],
      member_types: [],
      board: false,
      persons: [],
      names: 'managers',
      results: 'after_answer',
      closes_at: defaultEnd(),
      remind_days: '1',
      keep_months: '12',
      questions: [emptyQuestion('single')],
    }
  }
  return {
    title: s.title,
    description: s.description,
    event: s.event,
    audience: s.audience,
    departments: s.filters.departments ?? [],
    member_types: s.filters.member_types ?? [],
    board: !!s.filters.board,
    persons: (s.persons_named ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      first_name: p.name,
      last_name: '',
    })),
    names: s.names,
    results: s.results,
    closes_at: local(s.closes_at),
    remind_days: s.remind_days ? String(s.remind_days) : '',
    keep_months: String(s.keep_months),
    questions: s.questions ?? [],
  }
}

function payload(f: Form) {
  return {
    title: f.title,
    description: f.description,
    event: f.event,
    audience: f.audience,
    filters: { departments: f.departments, member_types: f.member_types, board: f.board },
    persons: f.persons.map((p) => p.id),
    names: f.names,
    results: f.results,
    closes_at: toApiTime(f.closes_at),
    remind_days: f.remind_days ? Number(f.remind_days) : null,
    keep_months: Number(f.keep_months) || 12,
    questions: f.questions.map((q) => ({
      kind: q.kind,
      text: q.text,
      required: q.required,
      max_choices: q.max_choices,
      allow_maybe: q.allow_maybe,
      options: q.options.map((o) => ({
        label: o.label,
        starts_at: o.starts_at,
        ends_at: o.ends_at,
        all_day: o.all_day,
        capacity: o.capacity,
      })),
    })),
  }
}

function toggle(list: number[], id: number, on: boolean) {
  return on ? [...list, id] : list.filter((x) => x !== id)
}

export function SurveyEditor({
  base,
  survey,
  onDone,
}: {
  base: string
  survey: Survey | null
  onDone: (saved: Survey | null) => Promise<void> | void
}) {
  const [form, setForm] = useState<Form>(() => toForm(survey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [count, setCount] = useState<number | null>(null)
  const [pick, setPick] = useState<SurveyMember | null>(null)
  const choices = useLoad(() => surveyApi.choices(base), [base])
  const c: SurveyChoices | null = choices.data
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    setCount(null)
  }
  const setQuestion = (i: number, q: SurveyQuestion) =>
    set(
      'questions',
      form.questions.map((x, j) => (j === i ? q : x)),
    )
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const data = payload(form)
      await onDone(
        survey ? await surveyApi.update(base, survey, data) : await surveyApi.create(base, data),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const eventChosen = form.event != null
  return (
    <form className="card stack" onSubmit={submit}>
      <h2>{survey ? t('Umfrage bearbeiten') : t('Neue Umfrage')}</h2>
      {!survey && (
        <div className="button-row" role="group" aria-label={t('Vorlage')}>
          {(['dates', 'meal', 'ride', 'opinion', 'free'] as Template[]).map((tpl) => (
            <button
              key={tpl}
              type="button"
              className="button button-ghost"
              onClick={() => {
                const made = fromTemplate(tpl)
                setForm((f) => ({
                  ...f,
                  questions: made.questions,
                  names: made.names,
                  title: f.title || templateLabel(tpl),
                  audience: tpl === 'meal' && f.event ? 'event_yes' : f.audience,
                }))
              }}
            >
              {templateLabel(tpl)}
            </button>
          ))}
        </div>
      )}
      <div className="survey-fields">
        <label className="field">
          <span>{t('Titel')}</span>
          <input
            value={form.title}
            maxLength={200}
            required
            onChange={(e) => set('title', e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Ende')}</span>
          <input
            type="datetime-local"
            required
            value={form.closes_at}
            onChange={(e) => set('closes_at', e.target.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>{t('Beschreibung (optional)')}</span>
        <textarea
          rows={2}
          maxLength={5000}
          value={form.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </label>
      <h3>{t('Fragen')}</h3>
      {form.questions.map((q, i) => (
        <QuestionEditor
          key={i}
          q={q}
          onChange={(next) => setQuestion(i, next)}
          onRemove={
            form.questions.length > 1
              ? () =>
                  set(
                    'questions',
                    form.questions.filter((_, j) => j !== i),
                  )
              : undefined
          }
        />
      ))}
      {form.questions.length < 10 && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => set('questions', [...form.questions, emptyQuestion()])}
          >
            {t('Weitere Frage')}
          </button>
        </div>
      )}
      <h3>{t('Wer wird gefragt?')}</h3>
      <div className="survey-fields">
        <label className="field">
          <span>{t('Termin (optional)')}</span>
          <select
            value={form.event ?? ''}
            onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : null
              setForm((f) => ({
                ...f,
                event: id,
                audience: id ? (f.audience === 'members' ? 'event_yes' : f.audience) : 'members',
              }))
              setCount(null)
            }}
          >
            <option value="">{t('ohne Termin')}</option>
            {(c?.events ?? []).map((ev) => (
              <option key={ev.id} value={ev.id}>
                {dateLabel({ starts_at: ev.starts_at })} · {ev.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Zielgruppe')}</span>
          <select
            value={form.audience}
            onChange={(e) => set('audience', e.target.value as Audience)}
          >
            {eventChosen ? (
              <>
                <option value="event_yes">{t('wer zum Termin zugesagt hat')}</option>
                <option value="event">{t('alle Eingeladenen des Termins')}</option>
              </>
            ) : (
              <>
                <option value="members">{t('Mitglieder')}</option>
                <option value="persons">{t('ausgewählte Personen')}</option>
              </>
            )}
          </select>
        </label>
      </div>
      {form.audience === 'members' && c && (
        <div className="stack-sm">
          {c.board && (
            <label className="survey-choice">
              <input
                type="checkbox"
                checked={form.board}
                onChange={(e) => set('board', e.target.checked)}
              />
              <span>{t('nur der Vorstand')}</span>
            </label>
          )}
          {c.units.length > 0 && (
            <fieldset className="survey-question">
              <legend>{t('Nur diese Untereinheiten (keine Auswahl: alle)')}</legend>
              <div className="survey-inline">
                {c.units.map((u) => (
                  <label key={u.id} className="survey-choice">
                    <input
                      type="checkbox"
                      checked={form.departments.includes(u.id)}
                      onChange={(e) =>
                        set('departments', toggle(form.departments, u.id, e.target.checked))
                      }
                    />
                    <span>{u.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {c.member_types.length > 1 && (
            <fieldset className="survey-question">
              <legend>{t('Nur diese Mitgliedsarten (keine Auswahl: alle)')}</legend>
              <div className="survey-inline">
                {c.member_types.map((m) => (
                  <label key={m.id} className="survey-choice">
                    <input
                      type="checkbox"
                      checked={form.member_types.includes(m.id)}
                      onChange={(e) =>
                        set('member_types', toggle(form.member_types, m.id, e.target.checked))
                      }
                    />
                    <span>{m.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        </div>
      )}
      {form.audience === 'persons' && (
        <div className="stack-sm">
          <ul className="plain-list">
            {form.persons.map((p) => (
              <li key={p.id}>
                {p.name}{' '}
                <button
                  type="button"
                  className="link-button small"
                  onClick={() =>
                    set(
                      'persons',
                      form.persons.filter((x) => x.id !== p.id),
                    )
                  }
                >
                  {t('Entfernen')}
                </button>
              </li>
            ))}
          </ul>
          <MemberPicker<SurveyMember>
            orgId={0}
            value={pick}
            label={t('Person hinzufügen')}
            search={(term) => surveyApi.members(base, term)}
            onChange={(m) => {
              setPick(null)
              if (m && !form.persons.some((p) => p.id === m.id)) {
                set('persons', [
                  ...form.persons,
                  { ...m, name: m.name ?? `${m.first_name} ${m.last_name}` },
                ])
              }
            }}
          />
        </div>
      )}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={async () => {
            try {
              setCount((await surveyApi.count(base, payload(form))).count)
            } catch (err) {
              setError(errorMessage(err))
            }
          }}
        >
          {t('Wie viele werden gefragt?')}
        </button>
        {count !== null && <span>{t('{n} Personen', { n: count })}</span>}
      </div>
      <h3>{t('Namen und Ergebnis')}</h3>
      <div className="aid-row">
        <Why k="survey_anonymous" />
      </div>
      <div className="survey-fields">
        <label className="field">
          <span>{t('Namen')}</span>
          <select
            value={form.names}
            onChange={(e) => {
              const names = e.target.value as NamesMode
              // Anonym: Ergebnis erst nach dem Ende (FF-22); strengere Wahl bleibt
              setForm((f) => ({
                ...f,
                names,
                results:
                  names === 'anonymous' && !ANONYMOUS_RESULTS.includes(f.results)
                    ? 'after_close'
                    : f.results,
              }))
              setCount(null)
            }}
          >
            {(['open', 'managers', 'anonymous'] as NamesMode[]).map((m) => (
              <option key={m} value={m}>
                {namesLabel(m)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Befragte sehen das Ergebnis')}</span>
          <select
            value={form.results}
            onChange={(e) => set('results', e.target.value as ResultsMode)}
          >
            {(form.names === 'anonymous'
              ? ANONYMOUS_RESULTS
              : (['after_answer', 'always', 'after_close', 'managers'] as ResultsMode[])
            ).map((m) => (
              <option key={m} value={m}>
                {resultsLabel(m)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('Erinnerung Tage vor dem Ende (leer: keine)')}</span>
          <input
            type="number"
            min={1}
            max={14}
            value={form.remind_days}
            onChange={(e) => set('remind_days', e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Antworten mit Namen löschen nach Monaten')}</span>
          <input
            type="number"
            min={1}
            max={60}
            value={form.keep_months}
            onChange={(e) => set('keep_months', e.target.value)}
          />
        </label>
      </div>
      {form.names === 'anonymous' && (
        <p className="muted small">
          {t(
            'Anonym: Niemand sieht, wer was geantwortet hat, auch die Verwaltung nicht. Antworten lassen sich nicht ändern, und das Ergebnis erscheint erst ab fünf Antworten.',
          )}{' '}
          {t('Das Ergebnis erscheint erst nach dem Ende, auch für die Verwaltung.')}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
        <button className="button button-primary" disabled={busy || !form.title.trim()}>
          {t('Speichern')}
        </button>
      </div>
    </form>
  )
}
