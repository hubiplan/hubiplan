import { Link } from 'react-router-dom'
import {
  competitionsApi,
  type CompetitionDetail,
  type ShootingProgram,
  type TargetCatalog,
} from '../../api/competitions.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SelectField } from '../../components/ui.tsx'
import { TargetSettings } from './TargetSettings.tsx'
import { t } from '../../i18n/index.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'

export function ProgramsSetup({
  org,
  comp,
  reload,
}: {
  org: number
  comp: CompetitionDetail
  reload: () => void
}) {
  const catalog = useLoad(() => competitionsApi.targets(org), [org])
  const action = useForm({})
  if (catalog.error) return <LoadError message={catalog.error} onRetry={catalog.reload} />
  if (!catalog.data) return <p>{t('Wird geladen …')}</p>
  const editable = comp.can_manage && comp.status !== 'endgueltig'
  return (
    <div className="stack">
      <p>
        {t(
          'Scheibe und Schusszahl gelten gemeinsam für alle Wertungen dieses Durchgangs. Getrennt geschossene Ergebnisse erhalten einen eigenen Durchgang.',
        )}
      </p>
      <p className="muted small">
        <Link to="/einstellungen/organisation">
          {t('Schießinfrastruktur des Vereins einstellen')}
        </Link>
      </p>
      {(comp.programs ?? []).map((program) => (
        <ProgramCard
          key={`${program.id}-${JSON.stringify(program)}`}
          org={org}
          comp={comp}
          program={program}
          catalog={catalog.data!}
          reload={reload}
        />
      ))}
      {(comp.programs ?? []).length === 0 && (
        <p>
          {t(
            'Noch keine Schießbedingungen eingerichtet. Lege einen Durchgang an oder füge eine Einzelwertung hinzu.',
          )}
        </p>
      )}
      {editable && (
        <button
          type="button"
          className="button button-ghost"
          disabled={action.busy}
          onClick={() =>
            void action.submit(async () => {
              await competitionsApi.createProgram(org, comp.id, {
                name: t('Schießdurchgang'),
                shots: 5,
              })
              reload()
            })
          }
        >
          {t('Weiteren Schießdurchgang anlegen')}
        </button>
      )}
      {action.message?.kind === 'error' && <Alert kind="error">{action.message.text}</Alert>}
    </div>
  )
}

function ProgramCard({
  org,
  comp,
  program,
  catalog,
  reload,
}: {
  org: number
  comp: CompetitionDetail
  program: ShootingProgram
  catalog: TargetCatalog
  reload: () => void
}) {
  const form = useForm({
    name: program.name,
    target: program.target,
    custom_target: program.custom_target,
    shots: program.shots,
    position: program.position,
    distance: program.distance,
  })
  const { values: v, set, errors } = form
  const editable = comp.can_manage && comp.status !== 'endgueltig'
  const chosen = catalog.targets.find((target) => target.key === v.target)
  const linked = comp.scorings.filter((s) => s.program === program.id)
  const changed =
    JSON.stringify(v) !==
    JSON.stringify({
      name: program.name,
      target: program.target,
      custom_target: program.custom_target,
      shots: program.shots,
      position: program.position,
      distance: program.distance,
    })
  const conditionsChanged =
    v.target !== program.target ||
    JSON.stringify(v.custom_target) !== JSON.stringify(program.custom_target) ||
    v.shots !== program.shots ||
    v.position !== program.position ||
    v.distance !== program.distance
  useDraftGuard(changed, () =>
    form.setValues({
      name: program.name,
      target: program.target,
      custom_target: program.custom_target,
      shots: program.shots,
      position: program.position,
      distance: program.distance,
    }),
  )

  async function save() {
    if (
      program.has_results &&
      conditionsChanged &&
      !(await confirmDialog({
        title: t('Schießbedingungen ändern'),
        message: t(
          'Die Änderung betrifft {n} Wertungen. Ergebnisse aus Treffern werden neu berechnet. Manuell eingegebene Summen bleiben erhalten und müssen geprüft werden. Noch nicht übertragene Offline-Eingaben unter den alten Bedingungen werden verworfen.',
          { n: linked.length },
        ),
        confirmLabel: t('Ändern und neu berechnen'),
      }))
    )
      return
    const saved = await form.submit(() =>
      competitionsApi.updateProgram(org, comp.id, program.id, {
        ...v,
        confirm_recalculation: program.has_results && conditionsChanged,
      }),
    )
    if (saved) reload()
  }

  async function remove() {
    if (
      !(await confirmDialog({
        title: t('Schießdurchgang löschen'),
        message: t('Den ungenutzten Durchgang „{name}“ löschen?', { name: program.name }),
        confirmLabel: t('Löschen'),
      }))
    )
      return
    try {
      await competitionsApi.removeProgram(org, comp.id, program.id)
      reload()
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <form
      className="card card-wide stack"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <div>
        <h2>
          {(comp.programs?.length ?? 0) === 1 ? t('Gemeinsame Schießbedingungen') : program.name}
        </h2>
        <p className="muted small">
          {linked.map((s) => s.name).join(' · ') || t('Noch keiner Wertung zugeordnet')}
        </p>
      </div>
      <fieldset disabled={!editable || form.busy} className="stack">
        {(comp.programs?.length ?? 0) > 1 && (
          <Field
            label={t('Bezeichnung des Durchgangs')}
            value={v.name}
            error={errors.name}
            onChange={(e) => set('name', e.target.value)}
          />
        )}
        <TargetSettings
          catalog={catalog}
          mode="conditions"
          values={{ ...v, method: 'frei', tie_breaks: [], series_size: 10 }}
          set={(key, value) => {
            if (key === 'target') {
              set('target', value as string)
              set('distance', null)
            }
            if (key === 'custom_target')
              set('custom_target', value as ShootingProgram['custom_target'])
          }}
          errors={errors}
        />
        {chosen && (
          <p className="setup-derived" aria-live="polite">
            {chosen.group} · {(chosen.distances ?? []).join(' / ')} m ·{' '}
            {String(chosen.caliber).replace('.', ',')} mm — {t('aus der Scheibe übernommen')}
          </p>
        )}
        <Field
          label={t('Schüsse pro Person')}
          type="number"
          min={1}
          max={200}
          value={v.shots ?? ''}
          error={errors.shots}
          onChange={(e) => set('shots', e.target.value ? Number(e.target.value) : null)}
        />
        <details>
          <summary>{t('Weitere Schießbedingungen')}</summary>
          <div className="grid-2">
            <Field
              label={t('Anschlagart (optional)')}
              placeholder={t('z. B. aufgelegt oder freihändig')}
              value={v.position}
              error={errors.position}
              onChange={(e) => set('position', e.target.value)}
            />
            {(chosen?.distances?.length ?? 0) > 1 ? (
              <SelectField
                label={t('Entfernung')}
                value={v.distance ?? ''}
                error={errors.distance}
                onChange={(e) => set('distance', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t('Nicht angegeben')}</option>
                {chosen!.distances!.map((distance) => (
                  <option key={distance} value={distance}>
                    {distance} m
                  </option>
                ))}
              </SelectField>
            ) : (
              !chosen && (
                <Field
                  label={t('Entfernung in m (optional)')}
                  type="number"
                  min={1}
                  value={v.distance ?? ''}
                  error={errors.distance}
                  onChange={(e) => set('distance', e.target.value ? Number(e.target.value) : null)}
                />
              )
            )}
          </div>
        </details>
        {editable && (
          <div className="button-row">
            <button type="submit" className="button" disabled={!changed}>
              {t('Schießbedingungen übernehmen')}
            </button>
            {linked.length === 0 && !program.has_results && (
              <button type="button" className="button button-ghost" onClick={() => void remove()}>
                {t('Durchgang löschen')}
              </button>
            )}
          </div>
        )}
      </fieldset>
      {changed && (
        <p className="muted small" role="status">
          {t('Änderungen noch nicht übernommen.')}
        </p>
      )}
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
    </form>
  )
}
