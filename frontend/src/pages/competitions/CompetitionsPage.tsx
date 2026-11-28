// Wettbewerbe: Liste, Einrichten (Grunddaten, Wertungen), Erfassen und Auswertung.
import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import {
  competitionsApi,
  orgStandApi,
  STATUS_LABELS,
  type Competition,
  type CompetitionDetail,
  type CompetitionStatus,
} from '../../api/competitions.ts'
import { PERM } from '../../api/orgs.ts'
import { ShootingSetupPage } from '../settings/OrganizationPage.tsx'
import { DataTable } from '../../components/DataTable.tsx'
import { choiceDialog, confirmDialog } from '../../components/dialog.ts'
import { useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, SelectField, Tabs, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { BirdStand } from './BirdStand.tsx'
import { EventPicker } from './CalendarLink.tsx'
import { ManualPrizes, StandAccessCard } from './BirdSetup.tsx'
import { ForeignPanel } from './ForeignPanel.tsx'
import { ResultsPanel } from './ResultsPanel.tsx'
import { CompetitionStatisticsPage } from './Statistics.tsx'
import { certificatesApi } from '../../api/certificates.ts'
import { CertificatesCard, CertificateTemplatesPage } from './Certificates.tsx'
import { GrantsCard } from './GrantsCard.tsx'
import { SeriesListPage } from './SeriesListPage.tsx'
import { SeriesPage } from './SeriesPage.tsx'
import { TitlesPage } from './TitlesPage.tsx'
import { TrophiesPage } from './TrophiesPage.tsx'
import { StandPanel } from './StandPanel.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { Checklist } from '../../learning/Checklist.tsx'
import { competitionFinishChecks } from '../../learning/checks.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useSportText } from './words.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { CompetitionSetup } from './CompetitionSetup.tsx'

export function CompetitionsPage() {
  return (
    <Routes>
      <Route index element={<CompetitionList />} />
      <Route path="statistik" element={<CompetitionStatisticsPage />} />
      <Route path="reihen" element={<SeriesListPage />} />
      <Route path="reihen/:id" element={<SeriesPage />} />
      <Route path="pokale" element={<TrophiesPage />} />
      <Route path="titel" element={<TitlesPage />} />
      <Route path="urkunden" element={<CertificateTemplatesPage />} />
      <Route path="einrichtung" element={<ShootingSetupPage />} />
      <Route path=":id/*" element={<CompetitionArea />} />
    </Routes>
  )
}

function CompetitionList() {
  const org = useActiveOrg()
  const navigate = useNavigate()
  const sw = useSportText()
  const canManage = org.permissions.includes(PERM.competitionsManage)
  const { data, error, reload } = useLoad(() => competitionsApi.list(org.id), [org.id])
  const [creating, setCreating] = useState(false)

  return (
    <section>
      <PageHeader name={t('Wettbewerbe')} />
      <p className="muted">
        {sw(
          'Eigene Schießen mit Einzel- und Zugwertung und Stechen, Vogelschießen mit Pfändern, und fremde Wettbewerbe, bei denen ihr eure Plätze eintragt.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      {canManage && !creating && (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setCreating(true)}>
            {t('Neuer Wettbewerb')}
          </button>
        </div>
      )}
      {creating && (
        <NewCompetition
          org={org.id}
          onClose={() => setCreating(false)}
          onCreated={(id) => navigate(`/wettbewerbe/${id}`)}
        />
      )}
      {data && (
        <DataTable<Competition>
          label={t('Wettbewerbe')}
          rows={data}
          rowKey={(c) => c.id}
          initialSort={{ key: 'date', dir: 'desc' }}
          emptyText={t('Noch keine Wettbewerbe.')}
          empty={
            creating ? undefined : (
              <EmptyList
                title={t('Noch keine Wettbewerbe.')}
                canAdd={canManage}
                action={{ label: t('Neuer Wettbewerb'), onClick: () => setCreating(true) }}
              />
            )
          }
          columns={[
            {
              key: 'date',
              label: t('Datum'),
              value: (c) => c.date,
              render: (c) => new Date(c.date).toLocaleDateString(locale()),
            },
            {
              key: 'title',
              label: t('Wettbewerb'),
              value: (c) => c.title,
              render: (c) => <Link to={`/wettbewerbe/${c.id}`}>{c.title}</Link>,
            },
            { key: 'occasion', label: t('Anlass'), value: (c) => c.occasion, optional: true },
            {
              key: 'starters',
              label: t('Starter'),
              value: (c) => c.starter_count,
              numeric: true,
            },
            {
              key: 'status',
              label: t('Zustand'),
              value: (c) => STATUS_LABELS[c.status],
              filter: true,
            },
          ]}
        />
      )}
    </section>
  )
}

/** Heutiges Datum (Ortszeit) als JJJJ-MM-TT */
function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function NewCompetition({
  org,
  onClose,
  onCreated,
}: {
  org: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const sw = useSportText()
  const shooting = useActiveOrg().modules.includes('shooting')
  const form = useForm({
    title: '',
    date: todayIso(),
    template: 'schiessen',
    organizer: '',
    event: '',
  })
  const { values: v, set, errors } = form

  async function save(e: FormEvent) {
    e.preventDefault()
    const { event, ...rest } = v
    const created = await form.submit(() =>
      competitionsApi.create(org, {
        ...rest,
        form: v.template === 'vogel' ? 'vogel' : 'rangliste',
        own: v.template !== 'fremd',
        ...(event === 'neu' ? { create_event: true } : event ? { event: Number(event) } : {}),
      }),
    )
    if (created) onCreated((created as Competition).id)
  }

  return (
    <div className="card card-wide">
      <form onSubmit={save}>
        <div className="card-head">
          <h2>{t('Neuer Wettbewerb')}</h2>
          <button type="button" className="button button-ghost push-right" onClick={onClose}>
            {t('Abbrechen')}
          </button>
        </div>
        <div className="grid-3">
          <Field
            label={t('Titel')}
            required
            placeholder={t('z. B. Preisschießen 2027')}
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
          <SelectField
            label={t('Vorlage')}
            value={v.template}
            onChange={(e) => set('template', e.target.value)}
          >
            <option value="schiessen">{sw('Schießen mit Einzel- und Zugwertung')}</option>
            <option value="einfach">{t('nur Einzelwertung')}</option>
            {shooting && <option value="vogel">{t('Vogelschießen mit Pfändern')}</option>}
            <option value="fremd">{t('Fremder Wettbewerb (eigene Plätze eintragen)')}</option>
            <option value="">{t('leer (Wertungen selbst anlegen)')}</option>
          </SelectField>
          <EventPicker
            org={org}
            value={v.event}
            onChange={(value, event) => {
              set('event', value)
              if (event) {
                set('title', event.title)
                set('date', event.date)
              }
            }}
          />
          {v.template === 'fremd' && (
            <Field
              label={t('Ausrichter')}
              placeholder={sw('z. B. Bürger-Schützenverein')}
              value={v.organizer}
              error={errors.organizer}
              onChange={(e) => set('organizer', e.target.value)}
            />
          )}
        </div>
        <Why k="comp_own" />
        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="submit" className="button" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </div>
      </form>
    </div>
  )
}

function CompetitionArea() {
  const sw = useSportText()
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const { data, error, reload, setData } = useLoad(
    () => competitionsApi.get(org.id, id),
    [org.id, id],
  )
  const standApi = useMemo(() => orgStandApi(org.id, id), [org.id, id])
  const [showAccess, setShowAccess] = useState(false)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const base = `/wettbewerbe/${id}`
  return (
    <section>
      <PageHeader title={data.title} />
      <p className="muted">
        {new Date(data.date).toLocaleDateString(locale())}
        {data.occasion ? t(' · {occasion}', { occasion: data.occasion }) : ''}
        {data.discipline ? t(' · {discipline}', { discipline: data.discipline }) : ''}
        {!data.own && data.organizer ? (
          <>
            {' '}
            · <Term k="comp_organizer">{t('Ausrichter')}</Term>: {data.organizer}
          </>
        ) : null}{' '}
        · {STATUS_LABELS[data.status]}
      </p>
      <Tabs
        items={[
          { to: base, label: t('Erfassen') },
          { to: `${base}/auswertung`, label: t('Auswertung') },
          { to: `${base}/einrichten`, label: t('Einrichten') },
        ]}
      />
      <Routes>
        <Route
          index
          element={
            <>
              <div className="button-row">
                {data.own && (
                  <a className="button button-ghost" href={`/stand/${org.id}/${id}`}>
                    {sw('Standmodus (Vollbild, Handy, offline)')}
                  </a>
                )}
                {data.own &&
                  (data.can_stand_access ?? data.can_manage) &&
                  data.status !== 'endgueltig' && (
                    <button
                      type="button"
                      className="button button-ghost"
                      aria-expanded={showAccess}
                      onClick={() => setShowAccess((v) => !v)}
                    >
                      {t('Anderes Gerät per QR-Code')}
                    </button>
                  )}
                <PrintMenu org={org.id} comp={data} />
              </div>
              {showAccess && data.own && (data.can_stand_access ?? data.can_manage) && (
                <StandAccessCard org={org.id} comp={data} />
              )}
              {!data.own ? (
                <ForeignPanel org={org.id} comp={data} />
              ) : data.form === 'vogel' ? (
                <>
                  <BirdStand
                    api={standApi}
                    comp={data}
                    onDrawAll={async () => {
                      await competitionsApi.drawAll(org.id, id)
                    }}
                  />
                  <ManualPrizes org={org.id} comp={data} />
                </>
              ) : (
                <StandPanel api={standApi} comp={data} />
              )}
            </>
          }
        />
        <Route
          path="auswertung"
          element={
            <>
              <ResultsPanel org={org.id} comp={data} onChanged={reload} />
              <CompetitionCompletion org={org.id} comp={data} reload={reload} />
              <GrantsCard org={org.id} comp={data} onChanged={reload} />
              {data.own && <CertificatesCard org={org.id} comp={data} />}
            </>
          }
        />
        <Route
          path="einrichten"
          element={
            <CompetitionSetup org={org.id} comp={data} onChanged={setData} reload={reload} />
          }
        />
        <Route path="*" element={<Navigate to={base} replace />} />
      </Routes>
    </section>
  )
}

export function PrintMenu({ org, comp }: { org: number; comp: CompetitionDetail }) {
  const sw = useSportText()
  async function print() {
    const choices = !comp.own
      ? [{ value: 'pdf', label: t('Ergebnisliste') }]
      : comp.form === 'vogel'
        ? [
            { value: 'losliste', label: t('Losliste (zum Zählen auf Papier)') },
            { value: 'pfaenderliste', label: t('Leere Pfänderliste') },
            { value: 'pdf', label: t('Pfänderliste mit Ergebnissen') },
          ]
        : [
            {
              value: 'schiessliste&sortierung=name',
              label: sw('Schießliste nach Name'),
              hint: sw('Zum Eintragen am Stand, erfasste Werte sind eingedruckt'),
            },
            {
              value: 'schiessliste&sortierung=einheit',
              label: sw('Schießliste nach Zug'),
              hint: sw('Je Zug eine Tabelle mit Feldern für die Zugwertung'),
            },
            {
              value: 'schiessliste&leer=1',
              label: sw('Leere Schießliste'),
              hint: t('Ohne Namen, für Nachmeldungen'),
            },
          ]
    if (comp.own) {
      choices.push(
        {
          value: 'startkarten&art=karten',
          label: t('Startkarten'),
          hint: sw('Vier Karten je Seite mit Startnummer und Kästchen für die Schüsse'),
        },
        {
          value: 'startkarten&art=aufkleber',
          label: t('Aufkleber für Startkarten'),
          hint: t('70 × 37 mm, 24 je Seite, für vorgedruckte Karten'),
        },
      )
    }
    // Nach dem Schießen zuerst die Ergebnisliste (Ralf 2026-11-01)
    if (comp.own && comp.form !== 'vogel') {
      const result = { value: 'pdf', label: t('Ergebnisliste'), hint: t('Plätze und Punkte') }
      if (comp.status === 'vorlaeufig' || comp.status === 'endgueltig') choices.unshift(result)
      else choices.push(result)
    }
    const choice = await choiceDialog({
      title: t('Drucken'),
      message: t('Welche Vorlage? (PDF zum Ausdrucken)'),
      choices,
      cancelValue: '',
    })
    if (!choice) return
    if (choice.startsWith('startkarten')) {
      const labels = choice.endsWith('aufkleber')
      window.open(certificatesApi.startCardsUrl(org, comp.id, labels, 'name'), '_blank')
      return
    }
    window.open(competitionsApi.exportUrl(org, comp.id, `als=${choice}`), '_blank')
  }
  return (
    <button type="button" className="button button-ghost" onClick={() => void print()}>
      {t('Drucken …')}
    </button>
  )
}

/** Prüfliste vor „Endgültig abschließen“; blockiert nichts (Lernhilfen Wettbewerbe). */
function CompetitionCompletion({
  org,
  comp,
  reload,
}: {
  org: number
  comp: CompetitionDetail
  reload: () => void
}) {
  const form = useForm({})
  if (!comp.can_manage) return null
  async function change(status: CompetitionStatus) {
    if (
      status === 'endgueltig' &&
      !(await confirmDialog({
        final: false,
        title: t('Endgültig abschließen'),
        message: t(
          'Die Ergebnisse werden endgültig abgeschlossen. Anschließend sind Eingaben gesperrt und freigegebene Ergebnisse werden veröffentlicht.',
        ),
        confirmLabel: t('Abschließen'),
      }))
    )
      return
    const result = await form.submit(() => competitionsApi.setStatus(org, comp.id, status))
    if (result) reload()
  }
  return (
    <section className="card card-wide">
      <h2>{t('Wettbewerb und Abschluss')}</h2>
      <p>
        {t('Zustand:')} {STATUS_LABELS[comp.status]}
        <span className="muted">
          {' '}
          {t('· erst')} <Term k="comp_provisional_term">{t('vorläufig')}</Term>
          {t(', nach dem Abschluss')} <Term k="comp_final_term">{t('endgültig')}</Term>
        </span>
      </p>
      {comp.own && comp.status !== 'endgueltig' && <FinishChecklist org={org} comp={comp} />}
      <div className="button-row">
        {comp.status === 'vorbereitung' && (
          <button
            type="button"
            className="button"
            disabled={form.busy}
            onClick={() => void change('laeuft')}
          >
            {t('Wettbewerb starten')}
          </button>
        )}
        {comp.status !== 'vorlaeufig' && comp.status !== 'endgueltig' && (
          <button
            type="button"
            className="button button-ghost"
            disabled={form.busy}
            onClick={() => void change('vorlaeufig')}
          >
            {t('Als vorläufig kennzeichnen')}
          </button>
        )}
        {comp.status === 'endgueltig' ? (
          <button
            type="button"
            className="button button-ghost"
            disabled={form.busy}
            onClick={() => void change('vorlaeufig')}
          >
            {t('Wieder öffnen')}
          </button>
        ) : (
          <button
            type="button"
            className="button"
            disabled={form.busy}
            onClick={() => void change('endgueltig')}
          >
            {t('Endgültig abschließen')}
          </button>
        )}
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <Why k="comp_provisional" />
      <Why k="comp_final" />
    </section>
  )
}

function FinishChecklist({ org, comp }: { org: number; comp: CompetitionDetail }) {
  const { data } = useLoad(() => competitionsApi.standings(org, comp.id), [org, comp.id])
  if (!data) return null
  return (
    <Checklist
      title={t('Vor dem endgültigen Abschluss')}
      items={competitionFinishChecks({
        missing: data.scorings
          .filter((b) => b.kind === 'einzel')
          .reduce((n, b) => n + b.without_value.length, 0),
        openShootoffs: data.open_shootoffs,
        bird: comp.form === 'vogel',
        hangingPrizes: data.bird ? data.bird.prizes.filter((p) => !p.winner_name).length : 0,
        website: comp.website,
      })}
    />
  )
}
