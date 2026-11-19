// Umfragen und Meinungsbilder: anlegen, starten, Ergebnis, Export (Verein und Untereinheit).
// Konzept: konzepte/umfragen-meinungsbilder.md.
import { useRowSort } from '../../components/RowSort.tsx'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { PERM } from '../../api/orgs.ts'
import { surveyApi } from '../../api/surveys.ts'
import type {
  Audience,
  NamesMode,
  QuestionKind,
  ResultsMode,
  Survey,
  SurveyChoices,
  SurveyMember,
  SurveyOption,
  SurveyQuestion,
  SurveyStatus,
} from '../../api/surveys.ts'
import { berlin } from '../../components/calendar/time.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { SurveyAnswerForm, SurveyResults, dateLabel, endText } from './SurveyParts.tsx'
import './surveys.css'
import { Why } from '../../learning/Aids.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { EmptyList } from '../../components/EmptyList.tsx'

export function statusLabel(status: SurveyStatus) {
  if (status === 'open') return t('läuft')
  if (status === 'closed') return t('beendet')
  return t('Entwurf')
}

function kindLabel(kind: QuestionKind) {
  switch (kind) {
    case 'single':
      return t('Einfachauswahl')
    case 'multiple':
      return t('Mehrfachauswahl')
    case 'yesno':
      return t('Ja / Nein / Enthaltung')
    case 'dates':
      return t('Terminfindung')
    case 'quantity':
      return t('Mengenauswahl (z. B. Essen)')
    default:
      return t('Freitext')
  }
}

const KINDS: QuestionKind[] = ['single', 'multiple', 'yesno', 'dates', 'quantity', 'text']

/** Anonyme Umfragen zeigen ihr Ergebnis erst nach dem Ende (Gesamtaudit 15.11., FF-22). */
const ANONYMOUS_RESULTS: ResultsMode[] = ['after_close', 'managers']

function namesLabel(mode: NamesMode) {
  if (mode === 'open') return t('offen: alle Befragten sehen Namen')
  if (mode === 'anonymous') return t('anonym: niemand sieht, wer was geantwortet hat')
  return t('nur die Verwaltung sieht Namen')
}

function resultsLabel(mode: ResultsMode) {
  if (mode === 'always') return t('immer')
  if (mode === 'after_close') return t('erst nach dem Ende')
  if (mode === 'managers') return t('nur die Verwaltung')
  return t('nach der eigenen Antwort')
}

/** Wert für ein datetime-local-Feld (deutsche Zeit) */
function local(value: string | null) {
  if (!value) return ''
  const b = berlin(value)
  return `${b.date}T${b.time}`
}

/** datetime-local → API (wird dort als deutsche Zeit gelesen) */
function toApiTime(value: string) {
  return value ? `${value}:00` : null
}

export function SurveysPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('surveys') : !!activeDept?.surveys_enabled
  if (!enabled || !permissions.includes(PERM.surveysView)) {
    return <NoAccessPage reason="right" />
  }
  const base = active ? `/api/orgs/${active.id}/surveys/` : `/api/depts/${activeDept!.id}/surveys/`
  return (
    <Surveys
      key={base}
      base={base}
      orgId={active?.id ?? activeDept!.id}
      canEdit={permissions.includes(PERM.surveysEdit)}
    />
  )
}

function Surveys({ base, orgId, canEdit }: { base: string; orgId: number; canEdit: boolean }) {
  const detail = useDetailParam('umfrage')
  const list = useLoad(() => surveyApi.list(base), [base])
  const [creating, setCreating] = useState(false)
  const sorting = useRowSort(list.data ?? [], {
    title: (s) => s.title,
    end: (s) => s.closes_at,
    answers: (s) => s.participants,
    status: (s) => s.status,
  })
  if (detail.value) {
    return (
      <SurveyDetail
        base={base}
        orgId={orgId}
        id={Number(detail.value)}
        onClose={async () => {
          detail.close()
          await list.reload()
        }}
        onOpen={async (id) => {
          await list.reload()
          detail.open(String(id))
        }}
      />
    )
  }
  const rows = sorting.rows
  return (
    <div className="surveys stack">
      <PageHeader
        primary={
          canEdit && !creating
            ? { label: t('Neue Umfrage'), onClick: () => setCreating(true) }
            : null
        }
      />
      <p className="muted">
        {t(
          'Umfragen sind Meinungsbilder, keine Beschlüsse: Termin finden, Essenswahl, wer fährt mit. Förmliche Abstimmungen gehören in die Versammlungen.',
        )}
      </p>
      <div className="aid-row">
        <Why k="survey_not_resolution" />
      </div>
      {creating && (
        <SurveyEditor
          base={base}
          survey={null}
          onDone={async (saved) => {
            setCreating(false)
            if (saved) {
              await list.reload()
              detail.open(String(saved.id))
            }
          }}
        />
      )}
      {list.error && <p role="alert">{list.error}</p>}
      {!list.data && !list.error && <Loading />}
      {list.data && rows.length === 0
        ? !creating && (
            <EmptyList
              title={t('Noch keine Umfrage.')}
              canAdd={canEdit}
              action={{ label: t('Neue Umfrage'), onClick: () => setCreating(true) }}
            />
          )
        : rows.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  {sorting.head('title', t('Umfrage'))}
                  {sorting.head('end', t('Ende'))}
                  {sorting.head('answers', t('Antworten'))}
                  {sorting.head('status', t('Stand'))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => detail.open(String(s.id))}
                      >
                        {s.title}
                      </button>
                      {s.event_title && <span className="muted small"> · {s.event_title}</span>}
                    </td>
                    <td>{endText(s.closes_at)}</td>
                    <td>
                      {s.invited != null
                        ? t('{n} von {m}', { n: s.participants, m: s.invited })
                        : s.participants}
                    </td>
                    <td>
                      <span className="badge">{statusLabel(s.status)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
    </div>
  )
}

function emptyOption(): SurveyOption {
  return { label: '', starts_at: null, ends_at: null, all_day: false, capacity: null }
}

function emptyQuestion(kind: QuestionKind = 'single'): SurveyQuestion {
  const options =
    kind === 'single' || kind === 'multiple' || kind === 'dates'
      ? [emptyOption(), emptyOption()]
      : kind === 'quantity'
        ? [emptyOption()]
        : []
  return { kind, text: '', required: true, max_choices: null, allow_maybe: true, options }
}

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

function SurveyEditor({
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

function QuestionEditor({
  q,
  onChange,
  onRemove,
}: {
  q: SurveyQuestion
  onChange: (q: SurveyQuestion) => void
  onRemove?: () => void
}) {
  const hasOptions = q.kind !== 'yesno' && q.kind !== 'text'
  const setOption = (i: number, o: SurveyOption) =>
    onChange({ ...q, options: q.options.map((x, j) => (j === i ? o : x)) })
  return (
    <div className="survey-editor-question stack-sm">
      <div className="survey-fields">
        <label className="field">
          <span>{t('Frage')}</span>
          <input
            value={q.text}
            maxLength={1000}
            required
            onChange={(e) => onChange({ ...q, text: e.target.value })}
          />
        </label>
        <label className="field">
          <span>{t('Art')}</span>
          <select
            value={q.kind}
            onChange={(e) => {
              const kind = e.target.value as QuestionKind
              onChange({ ...emptyQuestion(kind), text: q.text, required: q.required })
            }}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </select>
        </label>
        {(q.kind === 'multiple' || q.kind === 'quantity') && (
          <label className="field">
            <span>
              {q.kind === 'multiple'
                ? t('Höchstens so viele Antworten (leer: alle)')
                : t('Höchstens so viele Stück (ohne Termin)')}
            </span>
            <input
              type="number"
              min={1}
              max={50}
              value={q.max_choices ?? ''}
              onChange={(e) =>
                onChange({ ...q, max_choices: e.target.value ? Number(e.target.value) : null })
              }
            />
          </label>
        )}
      </div>
      <div className="survey-inline">
        <label className="survey-choice">
          <input
            type="checkbox"
            checked={q.required}
            onChange={(e) => onChange({ ...q, required: e.target.checked })}
          />
          <span>{t('Pflichtfrage')}</span>
        </label>
        {q.kind === 'dates' && (
          <label className="survey-choice">
            <input
              type="checkbox"
              checked={q.allow_maybe}
              onChange={(e) => onChange({ ...q, allow_maybe: e.target.checked })}
            />
            <span>{t('„Vielleicht“ erlaubt')}</span>
          </label>
        )}
      </div>
      {hasOptions &&
        q.options.map((o, i) => (
          <div key={i} className="survey-editor-option">
            {q.kind === 'dates' ? (
              <>
                <label className="field">
                  <span>{t('Vorschlag {n}', { n: i + 1 })}</span>
                  <input
                    type="datetime-local"
                    required
                    value={local(o.starts_at)}
                    onChange={(e) => setOption(i, { ...o, starts_at: toApiTime(e.target.value) })}
                  />
                </label>
                <label className="field">
                  <span>{t('Ende (optional)')}</span>
                  <input
                    type="datetime-local"
                    value={local(o.ends_at)}
                    onChange={(e) => setOption(i, { ...o, ends_at: toApiTime(e.target.value) })}
                  />
                </label>
              </>
            ) : (
              <>
                <label className="field">
                  <span>{t('Antwort {n}', { n: i + 1 })}</span>
                  <input
                    value={o.label}
                    maxLength={200}
                    required
                    onChange={(e) => setOption(i, { ...o, label: e.target.value })}
                  />
                </label>
                <label className="field survey-capacity">
                  <span>{t('Plätze')}</span>
                  <input
                    type="number"
                    min={1}
                    value={o.capacity ?? ''}
                    onChange={(e) =>
                      setOption(i, {
                        ...o,
                        capacity: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  />
                </label>
              </>
            )}
            {q.options.length > (q.kind === 'quantity' ? 1 : 2) && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => onChange({ ...q, options: q.options.filter((_, j) => j !== i) })}
              >
                {t('Entfernen')}
              </button>
            )}
          </div>
        ))}
      <div className="button-row">
        {hasOptions && q.options.length < 30 && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => onChange({ ...q, options: [...q.options, emptyOption()] })}
          >
            {q.kind === 'dates' ? t('Weiterer Vorschlag') : t('Weitere Antwort')}
          </button>
        )}
        {onRemove && (
          <button type="button" className="button button-ghost" onClick={onRemove}>
            {t('Frage entfernen')}
          </button>
        )}
      </div>
    </div>
  )
}

function SurveyDetail({
  base,
  orgId,
  id,
  onClose,
  onOpen,
}: {
  base: string
  orgId: number
  id: number
  onClose: () => void
  onOpen: (id: number) => Promise<void>
}) {
  const navigate = useNavigate()
  const loaded = useLoad(() => surveyApi.get(base, id), [base, id])
  const [editing, setEditing] = useState(false)
  const [entering, setEntering] = useState(false)
  const [member, setMember] = useState<SurveyMember | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [end, setEnd] = useState('')
  const s = loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!s) return <Loading />
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
      await loaded.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (editing) {
    return (
      <SurveyEditor
        base={base}
        survey={s}
        onDone={async (saved) => {
          setEditing(false)
          if (saved) await loaded.reload()
        }}
      />
    )
  }
  const dates = (s.questions ?? []).find((q) => q.kind === 'dates')
  const best = s.result?.questions.find((q) => q.kind === 'dates')?.best ?? []
  return (
    <div className="surveys stack">
      <PageHeader
        title={s.title}
        status={<span className="badge">{statusLabel(s.status)}</span>}
        onBack={onClose}
      />
      {s.description && <p>{s.description}</p>}
      <p className="muted">
        {s.event_title && `${s.event_title} · `}
        {s.closes_at && t('Ende: {x}', { x: endText(s.closes_at) })}
        {' · '}
        {namesLabel(s.names)}
        {' · '}
        {t('Ergebnis für Befragte: {x}', { x: resultsLabel(s.results) })}
      </p>
      {error && <p role="alert">{error}</p>}
      {s.can_edit && (
        <div className="button-row">
          {s.status === 'draft' && (
            <>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setEditing(true)}
              >
                {t('Bearbeiten')}
              </button>
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={async () => {
                  const okay = await confirmDialog({
                    title: t('Umfrage starten?'),
                    message: t(
                      'Alle Befragten bekommen Bescheid, per App oder per E-Mail. Fragen und Zielgruppe lassen sich danach nicht mehr ändern.',
                    ),
                    confirmLabel: t('Starten'),
                    danger: false,
                  })
                  if (okay) await run(() => surveyApi.start(base, s.id))
                }}
              >
                {t('Starten')}
              </button>
            </>
          )}
          {s.status === 'open' && (
            <>
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  const okay = await confirmDialog({
                    title: t('Umfrage beenden?'),
                    message: t('Danach kann niemand mehr antworten.'),
                    confirmLabel: t('Beenden'),
                    danger: false,
                  })
                  if (okay) await run(() => surveyApi.close(base, s.id))
                }}
              >
                {t('Jetzt beenden')}
              </button>
              {s.names !== 'anonymous' && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => setEntering(true)}
                >
                  {t('Für ein Mitglied eintragen')}
                </button>
              )}
            </>
          )}
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const copy = await surveyApi.copy(base, s.id)
                await onOpen(copy.id)
              })
            }
          >
            {t('Kopieren')}
          </button>
          {s.status !== 'open' && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={async () => {
                const okay = await confirmDialog({
                  final: true,
                  title: t('Umfrage löschen?'),
                  message: t('Die Umfrage und alle Antworten werden gelöscht.'),
                  confirmLabel: t('Löschen'),
                })
                if (okay) {
                  await run(() => surveyApi.remove(base, s.id))
                  onClose()
                }
              }}
            >
              {t('Löschen')}
            </button>
          )}
        </div>
      )}
      {s.status !== 'draft' && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () =>
                saveBlob(await surveyApi.export(base, s.id, 'pdf'), `umfrage-${s.id}.pdf`),
              )
            }
          >
            {t('PDF')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(async () =>
                saveBlob(await surveyApi.export(base, s.id, 'xlsx'), `umfrage-${s.id}.xlsx`),
              )
            }
          >
            {t('Excel')}
          </button>
        </div>
      )}
      {s.can_edit && s.status === 'open' && (
        <form
          className="button-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (end) run(() => surveyApi.update(base, s, { closes_at: toApiTime(end) }))
          }}
        >
          <label className="field">
            <span>{t('Ende verschieben')}</span>
            <input
              type="datetime-local"
              value={end || local(s.closes_at)}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <button className="button button-ghost" disabled={busy || !end}>
            {t('Übernehmen')}
          </button>
        </form>
      )}
      {entering && s.questions && (
        <div className="card stack">
          <h2>{t('Für ein Mitglied eintragen')}</h2>
          <MemberPicker<SurveyMember>
            orgId={orgId}
            value={member}
            label={t('Mitglied')}
            search={(term) => surveyApi.members(base, term)}
            onChange={setMember}
          />
          {member && (
            <SurveyAnswerForm
              key={member.id}
              questions={s.questions}
              mine={null}
              anonymous={false}
              busy={busy}
              submitLabel={t('Eintragen')}
              onCancel={() => setEntering(false)}
              onSubmit={(answers) =>
                run(async () => {
                  await surveyApi.answerFor(base, s.id, member.id, answers)
                  setEntering(false)
                  setMember(null)
                })
              }
            />
          )}
        </div>
      )}
      {s.status === 'draft' ? (
        <section className="card stack-sm">
          <h2>{t('Fragen')}</h2>
          <ul className="plain-list">
            {(s.questions ?? []).map((q) => (
              <li key={q.id}>
                <strong>{q.text}</strong> <span className="muted small">({kindLabel(q.kind)})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section className="card stack-sm">
          <h2>{t('Ergebnis')}</h2>
          <p className="muted small">
            {s.invited != null
              ? t('{n} von {m} haben geantwortet.', { n: s.participants, m: s.invited })
              : t('{n} haben geantwortet.', { n: s.participants })}{' '}
            {t('Meinungsbild, kein Beschluss.')}
          </p>
          {s.result && <SurveyResults result={s.result} />}
          {dates && s.can_create_event && !s.follow_event && (
            <div className="button-row">
              {dates.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className={best.includes(o.id!) ? 'button button-primary' : 'button button-ghost'}
                  disabled={busy}
                  onClick={async () => {
                    const okay = await confirmDialog({
                      title: t('Termin anlegen?'),
                      message: t(
                        'Aus „{x}“ entsteht ein Termin mit Zu- und Absagen. Wer hier „Ja“ gesagt hat, kann die Zusage mit einem Tipp übernehmen.',
                        { x: dateLabel(o) },
                      ),
                      confirmLabel: t('Termin anlegen'),
                      danger: false,
                    })
                    if (okay) await run(() => surveyApi.eventFrom(base, s.id, o.id!))
                  }}
                >
                  {t('Termin am {x} anlegen', { x: dateLabel(o) })}
                </button>
              ))}
            </div>
          )}
          {s.follow_event && (
            <p>
              <button
                type="button"
                className="link-button"
                onClick={() => navigate(`/termine?termin=${s.follow_event}`)}
              >
                {t('Zum angelegten Termin')}
              </button>
            </p>
          )}
          {s.pending && s.pending.length > 0 && (
            <details>
              <summary>{t('Noch ohne Antwort ({n})', { n: s.pending.length })}</summary>
              <p className="small">{s.pending.join(', ')}</p>
            </details>
          )}
        </section>
      )}
    </div>
  )
}
