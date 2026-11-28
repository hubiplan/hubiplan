import { useState } from 'react'
import { helperApi } from '../../api/helpers.ts'
import type { Duty, Shift } from '../../api/helpers.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import './helpers.css'
import { AssignForm } from './AssignForm.tsx'
import { dayText, timeText } from './helpersHelpers.ts'
import { QualificationSelect } from './QualificationSelect.tsx'

function started(s: Shift) {
  return new Date(s.starts_at).getTime() <= Date.now()
}

function shiftText(s: Shift) {
  return `${dayText(s.starts_at)} ${timeText(s.starts_at)}–${timeText(s.ends_at)}`
}

export function DutyCard({
  base,
  orgId,
  duty,
  editable,
  canMark,
  units,
  qualifications,
  onChanged,
}: {
  base: string
  orgId: number
  duty: Duty
  editable: boolean
  canMark: boolean
  units: { id: number; name: string }[]
  qualifications: { id: number; name: string }[]
  onChanged: () => Promise<void>
}) {
  const [error, setError] = useState('')
  const [assigning, setAssigning] = useState<number | null>(null)
  const [quotaFor, setQuotaFor] = useState<number | null>(null)
  const act = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <section className="card stack" aria-labelledby={`duty-${duty.id}`}>
      <div className="duty-head">
        <h2 id={`duty-${duty.id}`}>{duty.name}</h2>
        {editable && (
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => {
              const yes = await confirmDialog({
                final: true,
                title: t('Dienst „{name}“ löschen?', { name: duty.name }),
                message: t('Die Schichten werden ebenfalls gelöscht.'),
                confirmLabel: t('Löschen'),
              })
              if (yes) await act(() => helperApi.removeDuty(base, duty.id))
            }}
          >
            {t('Dienst löschen')}
          </button>
        )}
      </div>
      {(duty.location || duty.min_age || duty.qualification_name) && (
        <p className="muted">
          {[
            duty.location,
            duty.min_age ? t('ab {age} Jahren', { age: duty.min_age }) : '',
            duty.qualification_name
              ? t('Voraussetzung: {name}', { name: duty.qualification_name })
              : '',
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      {editable && (qualifications.length > 0 || duty.qualification) && (
        <div className="duty-tools">
          <QualificationSelect
            label={t('Voraussetzung für „{name}“', { name: duty.name })}
            value={duty.qualification ? String(duty.qualification) : ''}
            options={
              duty.qualification && !qualifications.some((k) => k.id === duty.qualification)
                ? [...qualifications, { id: duty.qualification, name: duty.qualification_name }]
                : qualifications
            }
            onChange={(v) =>
              void act(() =>
                helperApi.updateDuty(base, duty.id, { qualification: v ? Number(v) : null }),
              )
            }
          />
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {duty.shifts.length > 0 && (
        <table className="table shift-table">
          <thead>
            <tr>
              <th>{t('Schicht')}</th>
              <th>{t('Besetzt')}</th>
              <th>{t('Eingeteilt')}</th>
            </tr>
          </thead>
          <tbody>
            {duty.shifts.map((s) => {
              const people = s.assignments.filter((a) => a.status === 'active')
              const label = shiftText(s)
              return (
                <tr key={s.id}>
                  <td>
                    {label}
                    {s.note && <div className="muted small">{s.note}</div>}
                  </td>
                  <td className={people.length < s.needed ? 'shift-open' : undefined}>
                    {t('{taken} von {needed}', { taken: people.length, needed: s.needed })}
                    {s.quotas.map((q) => (
                      <div key={q.id} className="muted small">
                        {t('Kontingent {unit}: {filled} von {count}', {
                          unit: q.unit,
                          filled: q.filled,
                          count: q.count,
                        })}
                      </div>
                    ))}
                  </td>
                  <td>
                    <ul className="people">
                      {people.map((a) => (
                        <li key={a.id}>
                          {a.name}
                          {a.external && <span className="badge">{t('extern')}</span>}
                          {a.quota && (
                            <span className="badge">
                              {s.quotas.find((q) => q.id === a.quota)?.unit}
                            </span>
                          )}
                          {a.phone && <span className="muted small"> {a.phone}</span>}
                          {a.qualification_issue && (
                            <span className="badge badge-open" title={t('Hinweis')}>
                              {a.qualification_issue}
                            </span>
                          )}
                          {canMark && started(s) && (
                            <label className="done-mark">
                              <input
                                type="checkbox"
                                checked={a.done === true}
                                onChange={(e) =>
                                  act(() =>
                                    helperApi.updateAssignment(base, a.id, {
                                      done: e.target.checked,
                                    }),
                                  )
                                }
                              />
                              <span>{t('geleistet')}</span>
                            </label>
                          )}
                          {editable && (
                            <button
                              type="button"
                              className="link-button"
                              aria-label={t('{name} aus der Schicht {shift} nehmen', {
                                name: a.name,
                                shift: label,
                              })}
                              onClick={() => act(() => helperApi.removeAssignment(base, a.id))}
                            >
                              {t('Entfernen')}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                    {quotaFor === s.id && (
                      <QuotaForm
                        base={base}
                        shift={s}
                        label={label}
                        units={units}
                        onDone={async (changed) => {
                          setQuotaFor(null)
                          if (changed) await onChanged()
                        }}
                      />
                    )}
                    {editable &&
                      quotaFor !== s.id &&
                      (assigning === s.id ? (
                        <AssignForm
                          base={base}
                          orgId={orgId}
                          label={label}
                          assign={(data) => helperApi.assign(base, s.id, data)}
                          onDone={async (changed) => {
                            setAssigning(null)
                            if (changed) await onChanged()
                          }}
                        />
                      ) : (
                        <div className="button-row">
                          <button
                            type="button"
                            className="button button-ghost"
                            aria-label={t('Person einteilen: {shift}', { shift: label })}
                            onClick={() => setAssigning(s.id)}
                          >
                            {t('Einteilen')}
                          </button>
                          {units.length > 0 && (
                            <button
                              type="button"
                              className="button button-ghost"
                              aria-label={t('Kontingent vergeben: {shift}', { shift: label })}
                              onClick={() => setQuotaFor(s.id)}
                            >
                              {t('Kontingent')}
                            </button>
                          )}
                          {people.length === 0 && (
                            <button
                              type="button"
                              className="button button-ghost"
                              aria-label={t('Schicht löschen: {shift}', { shift: label })}
                              onClick={() => act(() => helperApi.removeShift(base, s.id))}
                            >
                              {t('Schicht löschen')}
                            </button>
                          )}
                        </div>
                      ))}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {editable && <NewShifts base={base} duty={duty} onSaved={onChanged} />}
    </section>
  )
}

function NewShifts({
  base,
  duty,
  onSaved,
}: {
  base: string
  duty: Duty
  onSaved: () => Promise<void>
}) {
  const [day, setDay] = useState('')
  const [quick, setQuick] = useState('')
  const [needed, setNeeded] = useState('2')
  const [error, setError] = useState('')
  return (
    <form
      className="helper-form"
      aria-label={t('Schichten für {name} anlegen', { name: duty.name })}
      onSubmit={async (e) => {
        e.preventDefault()
        setError('')
        try {
          await helperApi.addShifts(base, duty.id, { day, quick, needed: Number(needed) || 1 })
          setQuick('')
          await onSaved()
        } catch (err) {
          setError(errorMessage(err))
        }
      }}
    >
      <div className="helper-fields">
        <label className="field">
          <span>{t('Tag')}</span>
          <input type="date" value={day} required onChange={(e) => setDay(e.target.value)} />
        </label>
        <label className="field">
          <span>{t('Zeiten')}</span>
          <input
            value={quick}
            required
            maxLength={300}
            placeholder={t('z. B. 14-18, 18-22, 22-02')}
            onChange={(e) => setQuick(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Personen je Schicht')}</span>
          <input
            type="number"
            min={1}
            max={500}
            value={needed}
            onChange={(e) => setNeeded(e.target.value)}
          />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button" disabled={!day || !quick.trim()}>
          {t('Schichten anlegen')}
        </button>
      </div>
    </form>
  )
}

function QuotaForm({
  base,
  shift,
  label,
  units,
  onDone,
}: {
  base: string
  shift: Shift
  label: string
  units: { id: number; name: string }[]
  onDone: (changed: boolean) => Promise<void>
}) {
  const [unit, setUnit] = useState(String(units[0]?.id ?? ''))
  const current = shift.quotas.find((q) => String(q.department) === unit)
  const [count, setCount] = useState(String(current?.count ?? 1))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return (
    <form
      className="assign-form stack"
      aria-label={t('Kontingent vergeben: {shift}', { shift: label })}
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError('')
        try {
          await helperApi.setQuota(base, shift.id, Number(unit), Number(count) || 0)
          await onDone(true)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <label className="field">
        <span>{t('Untereinheit')}</span>
        <select
          value={unit}
          onChange={(e) => {
            setUnit(e.target.value)
            const q = shift.quotas.find((x) => String(x.department) === e.target.value)
            setCount(String(q?.count ?? 1))
          }}
        >
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('Plätze (0 entfernt das Kontingent)')}</span>
        <input
          type="number"
          min={0}
          max={shift.needed}
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
          {t('Abbrechen')}
        </button>
        <button className="button button-primary" disabled={busy || !unit}>
          {t('Kontingent speichern')}
        </button>
      </div>
    </form>
  )
}
