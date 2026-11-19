// Gemeinsame Teile der Umfragen: beantworten (Mitgliederbereich, Mail-Link, Verwaltung) und
// Ergebnis anzeigen. Konzept: konzepte/umfragen-meinungsbilder.md.
import { useState } from 'react'
import type { FormEvent } from 'react'
import type {
  AnswerRow,
  DateValue,
  ResultOption,
  ResultQuestion,
  SurveyOption,
  SurveyQuestion,
  SurveyResult,
  YesNoValue,
} from '../../api/surveys.ts'
import { berlin, formatDay } from '../../components/calendar/time.ts'
import { t, tn } from '../../i18n/index.ts'
import './surveys.css'

export function dateLabel(o: {
  starts_at: string | null
  ends_at?: string | null
  all_day?: boolean
}) {
  if (!o.starts_at) return ''
  const start = berlin(o.starts_at)
  const day = formatDay(start.date)
  if (o.all_day) return day
  if (o.ends_at) {
    const end = berlin(o.ends_at)
    if (end.date === start.date)
      return t('{day}, {from}–{to} Uhr', { day, from: start.time, to: end.time })
  }
  return t('{day}, {time} Uhr', { day, time: start.time })
}

export function optionLabel(o: SurveyOption | ResultOption) {
  return o.label || dateLabel(o)
}

export function endText(closesAt: string | null) {
  if (!closesAt) return ''
  const end = berlin(closesAt)
  return t('{day}, {time} Uhr', { day: formatDay(end.date), time: end.time })
}

export function valueLabel(v: YesNoValue | DateValue) {
  if (v === 'yes') return t('Ja')
  if (v === 'no') return t('Nein')
  if (v === 'maybe') return t('Vielleicht')
  return t('Enthaltung')
}

type Draft = Record<number, AnswerRow>

function initial(questions: SurveyQuestion[], mine: AnswerRow[] | null): Draft {
  const out: Draft = {}
  for (const q of questions) {
    const own = mine?.find((m) => m.question === q.id)
    out[q.id!] = own ? { ...own } : { question: q.id! }
    if (q.kind === 'dates' && !out[q.id!].dates) {
      out[q.id!].dates = Object.fromEntries(q.options.map((o) => [String(o.id), 'no' as DateValue]))
    }
  }
  return out
}

function filled(q: SurveyQuestion, row: AnswerRow) {
  if (q.kind === 'single' || q.kind === 'multiple') return (row.options ?? []).length > 0
  if (q.kind === 'yesno') return !!row.value
  if (q.kind === 'dates') return !!row.dates
  if (q.kind === 'quantity') return Object.values(row.quantities ?? {}).some((n) => n > 0)
  return !!row.text?.trim()
}

export function SurveyAnswerForm({
  questions,
  mine,
  anonymous,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  questions: SurveyQuestion[]
  mine: AnswerRow[] | null
  anonymous: boolean
  busy: boolean
  submitLabel?: string
  onSubmit: (answers: AnswerRow[]) => void
  onCancel?: () => void
}) {
  const [draft, setDraft] = useState<Draft>(() => initial(questions, mine))
  const set = (id: number, change: Partial<AnswerRow>) =>
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...change } }))
  const missing = questions.some((q) => q.required && !filled(q, draft[q.id!]))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit(questions.map((q) => draft[q.id!]).filter((row, i) => filled(questions[i], row)))
  }
  return (
    <form className="survey-form stack" onSubmit={submit}>
      {questions.map((q) => (
        <QuestionInput key={q.id} q={q} row={draft[q.id!]} set={(c) => set(q.id!, c)} />
      ))}
      {anonymous && (
        <p className="muted small">
          {t('Anonym. Deine Antwort lässt sich danach nicht mehr ändern.')}
        </p>
      )}
      <div className="button-row">
        {onCancel && (
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
        <button className="button button-primary" disabled={busy || missing}>
          {submitLabel ?? t('Absenden')}
        </button>
      </div>
    </form>
  )
}

function QuestionInput({
  q,
  row,
  set,
}: {
  q: SurveyQuestion
  row: AnswerRow
  set: (change: Partial<AnswerRow>) => void
}) {
  const legend = (
    <legend>
      {q.text}
      {!q.required && <span className="muted small"> {t('(freiwillig)')}</span>}
    </legend>
  )
  if (q.kind === 'single' || q.kind === 'multiple') {
    const chosen = row.options ?? []
    const multi = q.kind === 'multiple'
    return (
      <fieldset className="survey-question">
        {legend}
        {multi && q.max_choices && (
          <p className="muted small">{t('Höchstens {n} Antworten', { n: q.max_choices })}</p>
        )}
        {q.options.map((o) => (
          <label key={o.id} className="survey-choice">
            <input
              type={multi ? 'checkbox' : 'radio'}
              name={`q${q.id}`}
              checked={chosen.includes(o.id!)}
              onChange={(e) => {
                if (!multi) set({ options: [o.id!] })
                else if (e.target.checked) set({ options: [...chosen, o.id!] })
                else set({ options: chosen.filter((x) => x !== o.id) })
              }}
            />
            <span>{optionLabel(o)}</span>
            {o.capacity && (
              <span className="muted small">{t('{n} Plätze', { n: o.capacity })}</span>
            )}
          </label>
        ))}
        {!multi && !q.required && chosen.length > 0 && (
          <button type="button" className="link-button small" onClick={() => set({ options: [] })}>
            {t('Auswahl löschen')}
          </button>
        )}
      </fieldset>
    )
  }
  if (q.kind === 'yesno') {
    return (
      <fieldset className="survey-question">
        {legend}
        <div className="survey-inline">
          {(['yes', 'no', 'abstain'] as YesNoValue[]).map((v) => (
            <label key={v} className="survey-choice">
              <input
                type="radio"
                name={`q${q.id}`}
                checked={row.value === v}
                onChange={() => set({ value: v })}
              />
              <span>{valueLabel(v)}</span>
            </label>
          ))}
        </div>
      </fieldset>
    )
  }
  if (q.kind === 'dates') {
    const values: DateValue[] = q.allow_maybe ? ['yes', 'maybe', 'no'] : ['yes', 'no']
    return (
      <fieldset className="survey-question">
        {legend}
        <table className="table survey-dates">
          <tbody>
            {q.options.map((o) => (
              <tr key={o.id}>
                <th scope="row">{optionLabel(o)}</th>
                <td>
                  <div className="survey-inline">
                    {values.map((v) => (
                      <label key={v} className="survey-choice">
                        <input
                          type="radio"
                          name={`q${q.id}o${o.id}`}
                          checked={(row.dates ?? {})[String(o.id)] === v}
                          onChange={() => set({ dates: { ...row.dates, [String(o.id)]: v } })}
                        />
                        <span>{valueLabel(v)}</span>
                      </label>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </fieldset>
    )
  }
  if (q.kind === 'quantity') {
    const amounts = row.quantities ?? {}
    const total = Object.values(amounts).reduce((a, b) => a + b, 0)
    const max = q.max_total ?? q.max_choices ?? 1
    return (
      <fieldset className="survey-question">
        {legend}
        <p className="muted small">
          {tn('Zusammen höchstens {n} Stück', 'Zusammen höchstens {n} Stück', max)}
        </p>
        {q.options.map((o) => (
          <label key={o.id} className="survey-amount">
            <input
              type="number"
              min={0}
              max={max}
              value={amounts[String(o.id)] ?? 0}
              onChange={(e) =>
                set({
                  quantities: {
                    ...amounts,
                    [String(o.id)]: Math.max(0, Number(e.target.value) || 0),
                  },
                })
              }
            />
            <span>{optionLabel(o)}</span>
          </label>
        ))}
        {total > max && <p role="alert">{t('Zusammen höchstens {n} Stück.', { n: max })}</p>}
      </fieldset>
    )
  }
  return (
    <label className="field">
      <span>
        {q.text}
        {!q.required && <span className="muted small"> {t('(freiwillig)')}</span>}
      </span>
      <textarea
        maxLength={500}
        rows={3}
        value={row.text ?? ''}
        onChange={(e) => set({ text: e.target.value })}
      />
    </label>
  )
}

function Bar({ count, total }: { count: number; total: number }) {
  const share = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <span className="survey-bar" aria-hidden="true">
      <span style={{ width: `${share}%` }} />
    </span>
  )
}

export function SurveyResults({ result }: { result: SurveyResult }) {
  if (result.hidden && result.until_close) {
    return (
      <p className="muted">
        {t('Das Ergebnis erscheint nach dem Ende der Umfrage, damit niemand zurückrechnen kann.')}{' '}
        {tn('Bisher {n} Antwort.', 'Bisher {n} Antworten.', result.participants)}
      </p>
    )
  }
  if (result.hidden) {
    return (
      <p className="muted">
        {t('Das Ergebnis erscheint ab fünf Antworten, damit niemand zurückrechnen kann.')}{' '}
        {tn('Bisher {n} Antwort.', 'Bisher {n} Antworten.', result.participants)}
      </p>
    )
  }
  return (
    <div className="survey-results stack-sm">
      <p className="muted small">
        {tn('{n} Teilnahme', '{n} Teilnahmen', result.participants)}
        {result.archived
          ? ` · ${t('Antworten nach Ablauf der Frist gelöscht, Zahlen bleiben')}`
          : ''}
      </p>
      {result.questions.map((q) => (
        <ResultBlock key={q.id} q={q} total={result.participants} />
      ))}
    </div>
  )
}

function Names({ names }: { names: string[] }) {
  if (!names.length) return null
  return <span className="muted small survey-names">{names.join(', ')}</span>
}

function ResultBlock({ q, total }: { q: ResultQuestion; total: number }) {
  return (
    <section className="survey-result">
      <h3>{q.text}</h3>
      {q.kind === 'yesno' && q.values && (
        <ul className="plain-list">
          {(['yes', 'no', 'abstain'] as YesNoValue[]).map((v) => (
            <li key={v}>
              <span className="survey-result-label">{valueLabel(v)}</span>
              <Bar count={q.values![v].count} total={total} />
              <strong>{q.values![v].count}</strong>
              <Names names={q.values![v].names} />
            </li>
          ))}
        </ul>
      )}
      {q.kind === 'text' && (
        <ul className="plain-list survey-texts">
          {(q.texts ?? []).map((x, i) => (
            <li key={i}>
              „{x.text}“{x.name && <span className="muted small"> · {x.name}</span>}
            </li>
          ))}
          {!q.texts?.length && <li className="muted">{t('Noch keine Antworten.')}</li>}
        </ul>
      )}
      {q.options && (
        <ul className="plain-list">
          {q.options.map((o) => (
            <li key={o.id} className={q.best?.includes(o.id) ? 'survey-best' : undefined}>
              <span className="survey-result-label">{optionLabel(o)}</span>
              <Bar
                count={o.count}
                total={
                  q.kind === 'quantity' ? Math.max(1, ...q.options!.map((x) => x.count)) : total
                }
              />
              <strong>
                {o.count}
                {o.capacity ? ` / ${o.capacity}` : ''}
              </strong>
              {q.kind === 'dates' && !!o.maybe && (
                <span className="muted small">{t('+{n} vielleicht', { n: o.maybe })}</span>
              )}
              <Names names={o.names} />
              {o.maybe_names && o.maybe_names.length > 0 && (
                <span className="muted small survey-names">
                  {t('Vielleicht: {names}', { names: o.maybe_names.join(', ') })}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
