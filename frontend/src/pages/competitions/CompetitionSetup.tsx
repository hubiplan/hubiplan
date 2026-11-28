import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  competitionsApi,
  WEBSITE_DEPTH_LABELS,
  WEBSITE_LABELS,
  type Competition,
  type CompetitionDetail,
  type Detail,
  type Scoring,
  type WebsiteDepth,
  type WebsiteMode,
} from '../../api/competitions.ts'
import { choiceDialog, confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField } from '../../components/ui.tsx'
import { EventCard } from './CalendarLink.tsx'
import { PrizesCard } from './BirdSetup.tsx'
import { TemplateSelect } from './Certificates.tsx'
import { AwardsCard } from './AwardsCard.tsx'
import { SeriesSelect } from './SeriesSelect.tsx'
import { ProgramsSetup } from './ProgramsSetup.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { PlaceField } from '../../components/PlaceField.tsx'
import { useSportText } from './words.ts'
import { ScoringCard } from './ScoringCard.tsx'
import { numOrNull } from './competitionsHelpers.ts'

export function CompetitionSetup({
  org,
  comp,
  onChanged,
  reload,
}: {
  org: number
  comp: CompetitionDetail
  onChanged: (c: CompetitionDetail) => void
  reload: () => void
}) {
  const sw = useSportText()
  const navigate = useNavigate()
  const canManage = comp.can_manage && comp.status !== 'endgueltig'
  const [setupSection, setSetupSection] = useState('basic')
  const form = useForm({
    title: comp.title,
    occasion: comp.occasion,
    discipline: comp.discipline,
    location: comp.location,
    date: comp.date,
    description: comp.description,
    details: comp.details,
    website: comp.website,
    website_depth: comp.website_depth,
    // Webseite #149: leer = Adresse aus Titel und Jahr
    web_slug: comp.web_slug_auto === false ? (comp.web_slug ?? '') : '',
    share_ranking: comp.share_ranking,
    certificate_template: comp.certificate_template,
    series: comp.series,
    organizer: comp.organizer,
    drop_out: comp.drop_out,
    fixed_order: comp.fixed_order,
    total_shots: comp.total_shots,
    lots: comp.lots,
  })
  const { values: v, set, errors } = form
  const auto = useAutoSave(form, (changes) => competitionsApi.update(org, comp.id, changes), {
    enabled: canManage,
    onSaved: (saved) => onChanged({ ...comp, ...(saved as Competition) }),
  })

  function setDetail(i: number, d: Partial<Detail>) {
    set(
      'details',
      v.details.map((x, j) => (j === i ? { ...x, ...d } : x)),
    )
  }

  async function addScoring(data: Partial<Scoring>) {
    await form.submit(async () => {
      await competitionsApi.createScoring(org, comp.id, data)
      reload()
    })
  }

  async function reset() {
    const choice = await choiceDialog({
      title: t('Wettbewerb zurücksetzen'),
      message: t(
        'Bei „{title}“ alle erfassten Ergebnisse löschen (Werte, Stechen, Schüsse, gefallene Pfänder)? Regeln, Pfänder, Standzugang und Termin bleiben, der Zustand geht auf „Vorbereitung“. Das lässt sich nicht rückgängig machen.',
        { title: comp.title },
      ),
      choices: [
        { value: 'ergebnisse', label: t('Nur Ergebnisse löschen') },
        { value: 'alles', label: sw('Ergebnisse und Schützen löschen') },
      ],
      cancelValue: '',
    })
    if (!choice) return
    try {
      await competitionsApi.reset(org, comp.id, choice === 'ergebnisse')
      reload()
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function copy() {
    try {
      const res = await competitionsApi.copy(org, comp.id)
      navigate(`/wettbewerbe/${res.id}/einrichten`)
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Wettbewerb löschen'),
      message: sw('„{title}“ mit allen Startern, Ergebnissen und Stechen löschen?', {
        title: comp.title,
      }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await competitionsApi.remove(org, comp.id)
      navigate('/wettbewerbe')
    } catch (err) {
      form.setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  return (
    <>
      <nav className="button-row setup-navigation" aria-label={t('Wettbewerb einrichten')}>
        {[
          ['basic', t('Grunddaten')],
          ...(comp.own
            ? [
                [
                  'shooting',
                  comp.form === 'vogel' ? t('Pfänder & Ablauf') : sw('Schießbedingungen'),
                ],
              ]
            : []),
          ...(comp.form !== 'vogel' ? [['scorings', t('Wertungen')]] : []),
          ['output', t('Ausgabe & Freigabe')],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`button ${setupSection === key ? '' : 'button-ghost'}`}
            aria-current={setupSection === key ? 'page' : undefined}
            onClick={() => setSetupSection(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <div hidden={setupSection !== 'basic'}>
        <div className="card card-wide">
          <div className="card-head">
            <h2>{t('Grunddaten')}</h2>
            {canManage && <SaveStatus auto={auto} />}
          </div>
          <fieldset disabled={!canManage}>
            <div className="grid-3">
              <Field
                label={t('Titel')}
                required
                value={v.title}
                error={errors.title}
                onChange={(e) => set('title', e.target.value)}
              />
              <Field
                label={t('Datum')}
                type="date"
                required
                value={v.date}
                error={errors.date}
                onChange={(e) => set('date', e.target.value)}
              />
              <Field
                label={t('Anlass')}
                placeholder={t('z. B. Sommerfest')}
                value={v.occasion}
                error={errors.occasion}
                onChange={(e) => set('occasion', e.target.value)}
              />
              {(!comp.own || comp.form === 'vogel') && (
                <Field
                  label={t('Disziplin (optional)')}
                  placeholder={t('z. B. Luftgewehr')}
                  value={v.discipline}
                  error={errors.discipline}
                  onChange={(e) => set('discipline', e.target.value)}
                />
              )}
              <PlaceField
                label={t('Ort')}
                value={v.location}
                error={errors.location}
                onChange={(value) => set('location', value)}
              />
              {!comp.own && (
                <Field
                  label={t('Ausrichter')}
                  value={v.organizer}
                  error={errors.organizer}
                  onChange={(e) => set('organizer', e.target.value)}
                />
              )}
              <SeriesSelect
                org={org}
                value={v.series}
                disabled={!canManage}
                onChange={(id) => set('series', id)}
              />
            </div>
            <details>
              <summary>{t('Beschreibung und weitere Angaben')}</summary>
              <label className="field">
                <span>{t('Beschreibung')}</span>
                <textarea
                  rows={3}
                  value={v.description}
                  onChange={(e) => set('description', e.target.value)}
                />
              </label>
              <h3>{t('Weitere Angaben')}</h3>
              {v.details.map((d, i) => (
                <div className="grid-3" key={i}>
                  <Field
                    label={t('Angabe')}
                    placeholder={t('z. B. Entfernung')}
                    value={d.label}
                    onChange={(e) => setDetail(i, { label: e.target.value })}
                  />
                  <Field
                    label={t('Wert')}
                    placeholder={t('z. B. 10 m')}
                    value={d.value}
                    onChange={(e) => setDetail(i, { value: e.target.value })}
                  />
                  <div className="button-row">
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() =>
                        set(
                          'details',
                          v.details.filter((_, j) => j !== i),
                        )
                      }
                    >
                      {t('Entfernen')}
                    </button>
                  </div>
                </div>
              ))}
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => set('details', [...v.details, { label: '', value: '' }])}
                >
                  {t('Angabe hinzufügen')}
                </button>
              </div>
            </details>
          </fieldset>
        </div>

        <EventCard
          org={org}
          comp={comp}
          onChanged={(res) => {
            // Datum kommt aus dem Termin, Ort und Beschreibung, wenn sie leer waren
            if (res.date !== v.date) set('date', res.date)
            if (res.location !== v.location) set('location', res.location)
            if (res.description !== v.description) set('description', res.description)
            reload()
          }}
        />
      </div>
      {comp.own && (
        <div hidden={setupSection !== 'shooting'}>
          {comp.form === 'vogel' ? (
            <>
              <div className="card card-wide">
                <h2>{t('Vogelschießen')}</h2>
                <fieldset disabled={!canManage}>
                  <div className="grid-2">
                    <Checkbox
                      label={t('Wer ein Pfand errungen hat, scheidet aus')}
                      checked={v.drop_out}
                      onChange={(on) => set('drop_out', on)}
                    />
                    <Checkbox
                      label={t('Pfänder in fester Reihenfolge')}
                      checked={v.fixed_order}
                      onChange={(on) => set('fixed_order', on)}
                    />
                    <Field
                      label={sw('Schüsse insgesamt')}
                      type="number"
                      min={1}
                      hint={sw('nur, wenn auf Papier gezählt wurde; live zählt der Standmodus')}
                      value={v.total_shots ?? ''}
                      error={errors.total_shots}
                      onChange={(e) => set('total_shots', numOrNull(e.target.value))}
                    />
                    <Field
                      label={t('Lose im Hut')}
                      type="number"
                      min={1}
                      value={v.lots ?? ''}
                      error={errors.lots}
                      onChange={(e) => set('lots', numOrNull(e.target.value))}
                    />
                  </div>
                </fieldset>
                <Why k="comp_bird_rules" />
                <Why k="comp_lots" />
              </div>
              <PrizesCard org={org} comp={comp} onChanged={reload} />
            </>
          ) : (
            <ProgramsSetup org={org} comp={comp} reload={reload} />
          )}
        </div>
      )}
      <div hidden={setupSection !== 'scorings'}>
        {comp.form !== 'vogel' && <h2>{t('Wertungen')}</h2>}
        {comp.scorings.map((s) => (
          <ScoringCard
            key={`${s.id}-${JSON.stringify(s)}`}
            org={org}
            comp={comp}
            scoring={s}
            canManage={canManage}
            onRemoved={reload}
          />
        ))}
        {canManage && comp.form !== 'vogel' && (
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              onClick={() =>
                void addScoring({
                  name: t('Einzelwertung'),
                  kind: 'einzel',
                  ...(comp.own && comp.programs?.[0] ? { program: comp.programs[0].id } : {}),
                })
              }
            >
              {t('Einzelwertung hinzufügen')}
            </button>
            {!comp.own && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  void addScoring({
                    name: t('Mannschaftswertung'),
                    kind: 'mannschaft',
                  })
                }
              >
                {t('Mannschaftswertung hinzufügen')}
              </button>
            )}
            {comp.own && comp.scorings.some((s) => s.kind === 'einzel') && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  void addScoring({
                    name: t('Wertung der Untereinheiten'),
                    kind: 'einheit',
                    team_mode: 'beste',
                    team_size: 5,
                  })
                }
              >
                {t('Wertung der Untereinheiten hinzufügen')}
              </button>
            )}
          </div>
        )}
      </div>
      <div hidden={setupSection !== 'output'}>
        <div className="card card-wide">
          <div className="card-head">
            <h2>{t('Ausgabe & Freigabe')}</h2>
            {canManage && <SaveStatus auto={auto} />}
          </div>
          <fieldset disabled={!canManage}>
            <div className="grid-2">
              {comp.own && (
                <TemplateSelect
                  org={org}
                  value={v.certificate_template}
                  disabled={!canManage}
                  onChange={(id) => set('certificate_template', id)}
                />
              )}
              <SelectField
                label={t('Ergebnisse auf der Webseite')}
                value={v.website}
                onChange={(e) => set('website', e.target.value as WebsiteMode)}
              >
                {Object.entries(WEBSITE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </SelectField>
              {v.website !== 'aus' && (
                <SelectField
                  label={t('Öffentlich sichtbar')}
                  value={v.website_depth}
                  onChange={(e) => set('website_depth', e.target.value as WebsiteDepth)}
                >
                  {Object.entries(WEBSITE_DEPTH_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </SelectField>
              )}
              {v.website !== 'aus' && (
                <Field
                  label={t('Adresse auf der Webseite')}
                  value={v.web_slug}
                  placeholder={comp.web_slug || undefined}
                  error={errors.web_slug}
                  hint={t(
                    'Leer: aus Titel und Jahr, z. B. /ergebnisse/koenigsschiessen-2026/. Frühere Adressen leiten weiter.',
                  )}
                  onChange={(e) => set('web_slug', e.target.value)}
                />
              )}
            </div>
            <p className="setup-derived" aria-live="polite">
              {v.website === 'aus'
                ? t('Ergebnisse bleiben vereinsintern.')
                : `${WEBSITE_LABELS[v.website]} · ${WEBSITE_DEPTH_LABELS[v.website_depth]}`}
            </p>
            {comp.from_call && (
              <Checkbox
                label={t('Ganze Rangliste an die meldenden Untereinheiten')}
                hint={t(
                  'Diese Freigabe gilt für meldende Untereinheiten und ist von der öffentlichen Webseite unabhängig.',
                )}
                checked={v.share_ranking}
                onChange={(on) => set('share_ranking', on)}
              />
            )}
          </fieldset>
          <Why k="comp_website" />
        </div>
        <AwardsCard org={org} comp={comp} />
      </div>

      {comp.can_manage && (
        <details className="card card-wide">
          <summary>{t('Weitere Aktionen')}</summary>
          <div className="button-row">
            <button type="button" className="button button-ghost" onClick={() => void copy()}>
              {t('Für das nächste Jahr kopieren')}
            </button>
            {comp.status !== 'endgueltig' && (
              <button type="button" className="button button-danger" onClick={() => void reset()}>
                {t('Zurücksetzen …')}
              </button>
            )}
            <button type="button" className="button button-danger" onClick={() => void remove()}>
              {t('Löschen')}
            </button>
          </div>
          {comp.status !== 'endgueltig' && <Why k="comp_reset" />}
        </details>
      )}
    </>
  )
}
