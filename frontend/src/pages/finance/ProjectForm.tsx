import { useState } from 'react'
import type { FormEvent } from 'react'
import { financeApi } from '../../api/finance.ts'
import type { Project, ProjectEvaluation, ProjectSeries, ProjectStatus } from '../../api/finance.ts'
import { orgApi, unitName } from '../../api/orgs.ts'
import { promptDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'
import { STATUS } from './projectsHelpers.ts'

export function ProjectForm({
  project,
  series,
  onSeriesAdded,
  onSaved,
  onClose,
}: {
  project: Project | ProjectEvaluation | null
  series: ProjectSeries[]
  onSeriesAdded: () => void
  onSaved: (p: Project, done: boolean) => void
  onClose: () => void
}) {
  const org = useActiveOrg()
  const tm = useTerms()
  const departments = useLoad(
    () => (org.type === 'club' ? orgApi.departmentChoices(org.id) : Promise.resolve([])),
    [org.id, org.type],
  )
  const [extraSeries, setExtraSeries] = useState<ProjectSeries[]>([])
  const allSeries = [...series, ...extraSeries.filter((x) => !series.some((s) => s.id === x.id))]
  const form = useForm({
    name: project?.name ?? '',
    starts_on: project?.starts_on ?? '',
    ends_on: project?.ends_on ?? '',
    status: project?.status ?? 'planned',
    series: String(project?.series ?? ''),
    department: String(project && 'department' in project ? (project.department ?? '') : ''),
    description: project?.description ?? '',
    plan_income: project?.plan_income ?? '',
    plan_expense: project?.plan_expense ?? '',
  })
  const { values: v, errors, set } = form

  async function addSeries() {
    const name = await promptDialog({
      title: t('Neue Reihe'),
      message: t('Eine Reihe fasst wiederkehrende Veranstaltungen zusammen, z. B. „Sommerfest“.'),
      label: t('Name der Reihe'),
      confirmLabel: t('Anlegen'),
      danger: false,
    })
    if (!name?.trim()) return
    try {
      const s = await financeApi.createSeries(org.id, name.trim())
      setExtraSeries((prev) => [...prev, s])
      set('series', String(s.id))
      onSeriesAdded()
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  function payloadOf(x: typeof v) {
    return {
      name: x.name,
      starts_on: x.starts_on,
      ends_on: x.ends_on || null,
      status: x.status,
      series: x.series ? Number(x.series) : null,
      department: x.department ? Number(x.department) : null,
      description: x.description,
      plan_income: x.plan_income.trim() ? x.plan_income.replace(',', '.') : null,
      plan_expense: x.plan_expense.trim() ? x.plan_expense.replace(',', '.') : null,
    }
  }

  // Bestehende Veranstaltungen speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    form,
    (_changes, values) => financeApi.updateProject(org.id, project!.id, payloadOf(values)),
    { enabled: project !== null, onSaved: (saved) => onSaved(saved as Project, false) },
  )

  async function save(e: FormEvent) {
    e.preventDefault()
    if (project) {
      if (!(await auto.flush())) return
      onClose()
      return
    }
    const saved = await form.submit(() => financeApi.createProject(org.id, payloadOf(v)))
    if (saved) onSaved(saved as Project, true)
  }

  return (
    <div className="card card-wide">
      <form onSubmit={save}>
        <div className="card-head">
          <h2>{project ? t('Veranstaltung bearbeiten') : t('Neue Veranstaltung')}</h2>
          {project && <SaveStatus auto={auto} />}
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() =>
              void (project ? auto.flush() : Promise.resolve(true)).then((ok) => ok && onClose())
            }
          >
            {project ? t('Schließen') : t('Abbrechen')}
          </button>
        </div>
        <fieldset disabled={!project && form.busy}>
          <div className="grid-3">
            <Field
              label={t('Name')}
              required
              placeholder={t('z. B. Sommerfest 2026')}
              value={v.name}
              error={errors.name}
              onChange={(e) => set('name', e.target.value)}
            />
            <Field
              label={t('Beginn')}
              type="date"
              required
              value={v.starts_on}
              error={errors.starts_on}
              onChange={(e) => set('starts_on', e.target.value)}
            />
            <Field
              label={t('Ende (optional)')}
              type="date"
              value={v.ends_on}
              error={errors.ends_on}
              onChange={(e) => set('ends_on', e.target.value)}
            />
            <SelectField
              label={t('Status')}
              value={v.status}
              error={errors.status}
              onChange={(e) => set('status', e.target.value as ProjectStatus)}
            >
              {STATUS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={t('Reihe (optional)')}
              value={v.series}
              error={errors.series}
              hint={t('Für den Vergleich über die Jahre')}
              onChange={(e) => {
                if (e.target.value === '+') void addSeries()
                else set('series', e.target.value)
              }}
            >
              <option value="">{t('keine')}</option>
              {allSeries.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              <option value="+">{t('+ neue Reihe …')}</option>
            </SelectField>
            <Field
              label={t('geplante Einnahmen (optional)')}
              inputMode="decimal"
              value={v.plan_income}
              error={errors.plan_income}
              hint={t('Für den Vergleich von Plan und Ist')}
              onChange={(e) => set('plan_income', e.target.value)}
            />
            <Field
              label={t('geplante Ausgaben (optional)')}
              inputMode="decimal"
              value={v.plan_expense}
              error={errors.plan_expense}
              onChange={(e) => set('plan_expense', e.target.value)}
            />
            {(departments.data?.length ?? 0) > 0 && (
              <SelectField
                label={t('{sg} (optional)', { sg: tm.sg })}
                value={v.department}
                error={errors.department}
                onChange={(e) => set('department', e.target.value)}
              >
                <option value="">{t('keine')}</option>
                {departments.data!.map((d) => (
                  <option key={d.id} value={d.id}>
                    {unitName(d)}
                  </option>
                ))}
              </SelectField>
            )}
          </div>
          <label className="field">
            <span>{t('Beschreibung (optional)')}</span>
            <textarea
              rows={3}
              value={v.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </label>
        </fieldset>
        {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
        {!project && (
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={form.busy}>
              {t('Anlegen')}
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
