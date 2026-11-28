import { sendingVersion } from '../../api/client.ts'
import { competitionsApi, type CompetitionDetail, type Scoring } from '../../api/competitions.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { useForm, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { TargetSettings } from './TargetSettings.tsx'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { useSportText } from './words.ts'
import { numOrNull } from './competitionsHelpers.ts'

const TEAM_MODES = [
  { value: 'beste', label: t('Summe der besten') },
  { value: 'summe', label: t('Summe aller') },
  { value: 'durchschnitt', label: t('Durchschnitt aller') },
]

export function ScoringCard({
  org,
  comp,
  scoring,
  canManage,
  onRemoved,
}: {
  org: number
  comp: CompetitionDetail
  scoring: Scoring
  canManage: boolean
  onRemoved: () => void
}) {
  const sw = useSportText()
  const initial = {
    program: scoring.program,
    name: scoring.name,
    shots: scoring.shots,
    counted_shots: scoring.counted_shots,
    max_per_shot: scoring.max_per_shot,
    unit_label: scoring.unit_label,
    decimals: scoring.decimals,
    higher_better: scoring.higher_better,
    source: scoring.source,
    team_mode: scoring.team_mode,
    team_size: scoring.team_size,
    prize_places: scoring.prize_places,
    shootoff_shots: scoring.shootoff_shots,
    shootoff_counted: scoring.shootoff_counted,
    field_size: scoring.field_size,
    target: scoring.target ?? '',
    custom_target: scoring.custom_target ?? {},
    method: scoring.method ?? 'frei',
    tie_breaks: scoring.tie_breaks ?? [],
    series_size: scoring.series_size ?? 10,
  }
  const form = useForm(initial)
  const { values: v, set, errors } = form
  const needsConfirmation = scoring.has_results || !!errors.confirm_recalculation
  const changes = Object.fromEntries(
    Object.entries(v).filter(
      ([key, value]) =>
        JSON.stringify(value) !== JSON.stringify(initial[key as keyof typeof initial]),
    ),
  ) as Partial<typeof v>
  const dirty = JSON.stringify(v) !== JSON.stringify(initial)
  useDraftGuard(dirty, () => form.setValues(initial))
  const unit = scoring.kind === 'einheit'
  const singles = comp.scorings.filter((s) => s.kind === 'einzel')
  const foreign = !comp.own
  const single = !unit && !foreign
  // Scheiben gibt es nur mit dem Modul „Schießsport“
  const shooting = useActiveOrg().modules.includes('shooting')
  const catalog = useLoad(
    () => (single && shooting ? competitionsApi.targets(org) : Promise.resolve(null)),
    [org, single, shooting],
  )
  const fromHits = single && v.method !== 'frei'
  const program = comp.programs?.find((p) => p.id === v.program)
  const rulesChanged = Object.keys(v).some(
    (key) =>
      !['name', 'prize_places', 'shootoff_shots', 'shootoff_counted', 'field_size'].includes(key) &&
      JSON.stringify(v[key as keyof typeof v]) !==
        JSON.stringify(initial[key as keyof typeof initial]),
  )

  async function save() {
    if (
      needsConfirmation &&
      rulesChanged &&
      !(await confirmDialog({
        title: t('Wertungsregeln ändern'),
        message: t(
          'Vorhandene Ergebnisse aus Treffern werden mit den neuen Regeln berechnet. Manuelle Summen müssen geprüft werden. Die Änderung kann Ranglisten und Preisplätze verändern.',
        ),
        confirmLabel: t('Ändern und neu berechnen'),
        danger: false,
      }))
    )
      return
    const saved = await form.submit(() =>
      sendingVersion(scoring.version, () =>
        competitionsApi.updateScoring(org, comp.id, scoring.id, {
          ...changes,
          confirm_recalculation: !!needsConfirmation && rulesChanged,
        }),
      ),
    )
    if (saved) onRemoved()
  }

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Wertung löschen'),
      message: sw('„{name}“ mit allen Ergebnissen und Stechen löschen?', { name: scoring.name }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    await form.submit(async () => {
      await sendingVersion(scoring.version, () =>
        competitionsApi.removeScoring(org, comp.id, scoring.id),
      )
      onRemoved()
    })
  }

  return (
    <form
      className="card card-wide"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <div className="card-head">
        <h3>
          {unit ? (
            <Term k="comp_unit_scoring">{t('Wertung der Untereinheiten')}</Term>
          ) : scoring.kind === 'mannschaft' ? (
            t('Mannschaftswertung')
          ) : (
            t('Einzelwertung')
          )}
        </h3>
      </div>
      <p className="muted">
        {scoring.name}
        {program ? ` · ${program.name} · ${program.shots ?? '–'} ${sw('Schüsse')}` : ''}
      </p>
      {single && (
        <p>
          {v.method === 'teiler'
            ? v.counted_shots
              ? t('Summe der besten {n} Teiler; kleiner ist besser.', { n: v.counted_shots })
              : t('Der beste Teiler zählt; kleiner ist besser.')
            : v.counted_shots
              ? sw('Die besten {n} Schüsse zählen.', { n: v.counted_shots })
              : sw('Alle Schüsse zählen.')}
        </p>
      )}
      <details>
        <summary>{t('Wertung bearbeiten')}</summary>
        <fieldset disabled={!canManage || form.busy}>
          <div className="grid-3">
            <Field
              label={t('Bezeichnung')}
              value={v.name}
              error={errors.name}
              onChange={(e) => set('name', e.target.value)}
            />
            {foreign ? (
              <>
                <Field
                  label={t('Teilnehmer insgesamt')}
                  type="number"
                  min={1}
                  hint={t('für „Platz 2 von 14“')}
                  value={v.field_size ?? ''}
                  error={errors.field_size}
                  onChange={(e) => set('field_size', numOrNull(e.target.value))}
                />
                <Field
                  label={t('Einheit des Werts')}
                  value={v.unit_label}
                  error={errors.unit_label}
                  onChange={(e) => set('unit_label', e.target.value)}
                />
                <SelectField
                  label={t('Nachkommastellen')}
                  value={v.decimals}
                  onChange={(e) => set('decimals', Number(e.target.value))}
                >
                  {[0, 1, 2, 3].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </SelectField>
              </>
            ) : unit ? (
              <>
                <SelectField
                  label={t('Aus der Wertung')}
                  value={v.source ?? ''}
                  error={errors.source}
                  onChange={(e) => set('source', numOrNull(e.target.value))}
                >
                  {singles.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={t('Rechenweise')}
                  value={v.team_mode}
                  error={errors.team_mode}
                  onChange={(e) => set('team_mode', e.target.value as Scoring['team_mode'])}
                >
                  {TEAM_MODES.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </SelectField>
                {v.team_mode === 'beste' && (
                  <Field
                    label={t('Anzahl der besten')}
                    type="number"
                    min={1}
                    hint={sw('Weniger Schützen: die Einheit wird nicht gewertet.')}
                    value={v.team_size ?? ''}
                    error={errors.team_size}
                    onChange={(e) => set('team_size', numOrNull(e.target.value))}
                  />
                )}
              </>
            ) : (
              <>
                {program ? (
                  <SelectField
                    label={sw('Grundlage: Schießdurchgang')}
                    value={v.program ?? ''}
                    error={errors.program}
                    onChange={(e) => {
                      const p = comp.programs?.find((item) => item.id === Number(e.target.value))
                      if (p) {
                        set('program', p.id)
                        set('shots', p.shots)
                        set('target', p.target)
                        set('custom_target', p.custom_target)
                      }
                    }}
                  >
                    {comp.programs?.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </SelectField>
                ) : (
                  <Field
                    label={sw('Schüsse je Schütze')}
                    type="number"
                    min={1}
                    value={v.shots ?? ''}
                    error={errors.shots}
                    onChange={(e) => set('shots', numOrNull(e.target.value))}
                  />
                )}
                <SelectField
                  label={sw('Welche Schüsse zählen?')}
                  value={v.counted_shots === null ? 'all' : 'best'}
                  onChange={(e) =>
                    set(
                      'counted_shots',
                      e.target.value === 'all' ? null : Math.min(v.shots ?? 3, 3),
                    )
                  }
                >
                  <option value="all">
                    {v.method === 'teiler' ? t('Bester Teiler') : sw('Alle Schüsse')}
                  </option>
                  <option value="best">
                    {v.method === 'teiler' ? t('Summe der besten …') : t('Die besten …')}
                  </option>
                </SelectField>
                {v.counted_shots !== null && (
                  <Field
                    label={t('davon in der Wertung')}
                    type="number"
                    min={1}
                    value={v.counted_shots ?? ''}
                    error={errors.counted_shots}
                    onChange={(e) => set('counted_shots', numOrNull(e.target.value))}
                  />
                )}
                {!fromHits && (
                  <>
                    <Field
                      label={sw('Höchstwert je Schuss')}
                      inputMode="decimal"
                      value={v.max_per_shot ?? ''}
                      error={errors.max_per_shot}
                      onChange={(e) =>
                        set('max_per_shot', e.target.value.replace(',', '.') || null)
                      }
                    />
                    <Field
                      label={t('Einheit des Werts')}
                      value={v.unit_label}
                      error={errors.unit_label}
                      onChange={(e) => set('unit_label', e.target.value)}
                    />
                    <SelectField
                      label={t('Nachkommastellen')}
                      value={v.decimals}
                      onChange={(e) => set('decimals', Number(e.target.value))}
                    >
                      {[0, 1, 2, 3].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </SelectField>
                    <Checkbox
                      label={t('Größer ist besser')}
                      hint={t('aus bei Zeit oder Teiler')}
                      checked={v.higher_better}
                      onChange={(on) => set('higher_better', on)}
                    />
                  </>
                )}
              </>
            )}
            <Field
              label={t('Preisplätze')}
              type="number"
              min={0}
              value={v.prize_places}
              error={errors.prize_places}
              onChange={(e) => set('prize_places', numOrNull(e.target.value) ?? 0)}
            />
            {!foreign && (
              <Field
                label={sw('Schüsse im Stechen (Vorschlag)')}
                type="number"
                min={1}
                hint={sw('beim Anlegen des Stechens vor Ort änderbar')}
                value={v.shootoff_shots ?? ''}
                error={errors.shootoff_shots}
                onChange={(e) => set('shootoff_shots', numOrNull(e.target.value))}
              />
            )}
            {!unit && !foreign && (
              <Field
                label={t('davon gewertet (Vorschlag)')}
                type="number"
                min={1}
                value={v.shootoff_counted ?? ''}
                error={errors.shootoff_counted}
                onChange={(e) => set('shootoff_counted', numOrNull(e.target.value))}
              />
            )}
          </div>
          {!foreign && !unit && (
            <p className="muted small">
              {t('Mit')} <Term k="comp_counted">{sw('gewerteten Schüssen')}</Term>{' '}
              {t('und Höchstwert prüft HUBIplan jede Eingabe.')}
              {fromHits &&
                (v.method === 'teiler'
                  ? t(
                      ' Teiler: kleiner ist besser, es zählt der beste Teiler (bei mehreren gewerteten Schüssen ihre Summe).',
                    )
                  : sw(' Höchstwert je Schuss {x}, {x2}.', {
                      x: String(v.max_per_shot ?? '').replace('.', ','),
                      x2: v.decimals ? t('mit Zehnteln') : sw('ganze Ringe'),
                    }))}
            </p>
          )}
          {single && catalog.data && (
            <TargetSettings
              mode={program ? 'scoring' : 'all'}
              catalog={catalog.data}
              values={v}
              set={(key, value) => set(key, value as (typeof v)[typeof key])}
              errors={errors}
            />
          )}
          {!foreign && (unit ? <Why k="comp_team_mode" /> : <Why k="comp_shots" />)}
          {!foreign && <Why k="comp_prize_places" />}
          {canManage && (
            <div className="button-row">
              <button type="submit" className="button" disabled={!dirty}>
                {t('Wertungsregeln übernehmen')}
              </button>
              <button type="button" className="button button-ghost" onClick={() => void remove()}>
                {t('Wertung löschen')}
              </button>
            </div>
          )}
        </fieldset>
      </details>
      {dirty && (
        <p className="muted small" role="status">
          {t('Änderungen noch nicht übernommen.')}
        </p>
      )}
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
    </form>
  )
}
