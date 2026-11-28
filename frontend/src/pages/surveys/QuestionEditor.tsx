import type { QuestionKind, SurveyOption, SurveyQuestion } from '../../api/surveys.ts'
import { t } from '../../i18n/index.ts'
import './surveys.css'
import { emptyOption, emptyQuestion, kindLabel, local, toApiTime } from './surveysHelpers.ts'

const KINDS: QuestionKind[] = ['single', 'multiple', 'yesno', 'dates', 'quantity', 'text']

export function QuestionEditor({
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
