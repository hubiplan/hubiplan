import { Link, useSearchParams } from 'react-router-dom'
import { competitionStatisticsApi } from '../../api/competitionStatistics.ts'
import type {
  CompetitionStatisticsData,
  StatisticsMember,
  StatisticsQuery,
  StatisticsResult,
} from '../../api/competitionStatistics.ts'
import { DataTable } from '../../components/DataTable.tsx'
import { ChartCard, TimeChart } from '../../components/charts/Charts.tsx'
import { PRIMARY } from '../../components/charts/chartData.ts'
import { formatDate, useQueryLoad } from '../../components/forms.ts'
import { LoadError, SelectField } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import './statistics.css'

const number = (n: number | null | undefined, digits = 2) =>
  n == null ? '–' : n.toLocaleString(locale(), { maximumFractionDigits: digits })

export function CompetitionStatisticsPage() {
  const org = useActiveOrg()
  return (
    <section className="stack">
      <div>
        <h1>{t('Wettbewerbsstatistik')}</h1>
        <p className="muted">{t('Teilnahmen, Leistungen und Erfolge im Überblick.')}</p>
      </div>
      <CompetitionStatistics org={org.id} />
    </section>
  )
}

export function CompetitionStatistics({
  org,
  membership,
  accessId,
}: {
  org?: number
  membership?: number
  accessId?: number
}) {
  const [params, setParams] = useSearchParams()
  const query: StatisticsQuery = {
    year: params.get('stat_jahr') || '',
    form: params.get('stat_art') || '',
    group: params.get('stat_wertung') || '',
    ...(!membership && !accessId ? { membership: params.get('stat_mitglied') || '' } : {}),
  }
  const scope = `${org ?? ''}:${membership ?? ''}:${accessId ?? ''}`
  const key = JSON.stringify(query)
  const { data, error, reload } = useQueryLoad(
    () =>
      accessId
        ? competitionStatisticsApi.mine(accessId, query)
        : membership
          ? competitionStatisticsApi.member(org!, membership, query)
          : competitionStatisticsApi.all(org!, query),
    [scope, key],
  )
  const personal = !!(membership || accessId || query.membership)
  function filter(name: string, value: string) {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(name, value)
      else next.delete(name)
      // Eine neue Wettbewerbsart hat andere Wertungsbedingungen.
      if (name === 'stat_art') next.delete('stat_wertung')
      return next
    })
  }
  return (
    <div className="stack competition-statistics">
      <div className="card card-wide competition-statistics-filters">
        <div className="grid-3">
          {!membership && !accessId && (
            <SelectField
              label={t('Mitglied')}
              value={query.membership}
              onChange={(e) => filter('stat_mitglied', e.target.value)}
            >
              <option value="">{t('Alle Mitglieder')}</option>
              {(data?.member_options ?? []).map((m) => (
                <option key={m.membership} value={m.membership}>
                  {m.name}
                </option>
              ))}
            </SelectField>
          )}
          <SelectField
            label={t('Zeitraum')}
            value={query.year}
            onChange={(e) => filter('stat_jahr', e.target.value)}
          >
            <option value="">{t('Alle Jahre')}</option>
            {[...new Set([...(data?.years ?? []), ...(query.year ? [Number(query.year)] : [])])]
              .sort((a, b) => b - a)
              .map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
          </SelectField>
          <SelectField
            label={t('Wettbewerbsart')}
            value={query.form}
            onChange={(e) => filter('stat_art', e.target.value)}
          >
            <option value="">{t('Alle Arten')}</option>
            <option value="rangliste">{t('Ranglistenschießen')}</option>
            <option value="vogel">{t('Vogelschießen')}</option>
          </SelectField>
        </div>
        {((data?.groups.length ?? 0) > 0 || query.group) && (
          <SelectField
            label={t('Wertungsbedingungen')}
            value={query.group}
            onChange={(e) => filter('stat_wertung', e.target.value)}
          >
            <option value="">{t('Alle Bedingungen – getrennt ausgewertet')}</option>
            {(data?.groups ?? []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
            {query.group && !data?.groups.some((g) => g.id === query.group) && (
              <option value={query.group}>{t('Gewählte Bedingungen')}</option>
            )}
          </SelectField>
        )}
        <p className="muted small">
          {t('Nur endgültige Ergebnisse · Mitglieder ohne Gäste und außer Konkurrenz.')}
        </p>
      </div>
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!data && !error && (
        <p className="muted" role="status">
          {t('Lädt …')}
        </p>
      )}
      {data && (
        <StatisticsContent
          data={data}
          personal={personal}
          portal={!!accessId}
          onMember={(id) => filter('stat_mitglied', String(id))}
          onGroup={(id) => filter('stat_wertung', id)}
        />
      )}
    </div>
  )
}

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="card tile">
      <h2>{label}</h2>
      <p className="amount-big">{value}</p>
      {note && <p className="small muted">{note}</p>}
    </div>
  )
}

function StatisticsContent({
  data,
  personal,
  portal,
  onMember,
  onGroup,
}: {
  data: CompetitionStatisticsData
  personal: boolean
  portal: boolean
  onMember: (id: number) => void
  onGroup: (id: string) => void
}) {
  const { summary: s, performance: p, selected_group: group } = data
  const rings = group?.method === 'ringe' || group?.method === 'zehntel'
  const unit = group?.unit_label ?? ''
  const value = (n: number | null | undefined) => (n == null ? '–' : `${number(n)} ${unit}`)
  return (
    <>
      <div className="tiles tiles-figures competition-statistics-figures">
        <Figure
          label={t('Teilnahmen')}
          value={number(s.starts, 0)}
          note={t('{n} Wettbewerbe', { n: s.competitions })}
        />
        <Figure
          label={personal ? t('Siege') : t('Teilnehmende Mitglieder')}
          value={number(personal ? s.wins : s.members, 0)}
          note={personal ? t('Nur Einzelwertungen') : t('Jede Person einmal')}
        />
        <Figure
          label={t('Podestplätze')}
          value={number(s.podiums, 0)}
          note={t('Platz 1 bis 3 · Einzelwertungen')}
        />
        <Figure
          label={t('Errungene Pfänder')}
          value={number(s.prizes, 0)}
          note={t('Vogelschießen')}
        />
      </div>
      {group && p && (
        <section className="stack" aria-label={t('Leistungsstatistik')}>
          <div>
            <h2>{t('Leistung und Entwicklung')}</h2>
            <p className="muted small">{group.label}</p>
          </div>
          <div className="tiles tiles-figures competition-statistics-performance">
            <Figure
              label={rings ? t('Durchschnittliche Ringe') : t('Ergebnisdurchschnitt')}
              value={value(p.average)}
              note={t('Aus {n} gültigen Ergebnissen', { n: p.count })}
            />
            <Figure
              label={t('Bestleistung')}
              value={value(p.best)}
              note={
                personal
                  ? group.maximum == null
                    ? undefined
                    : t('Maximal {n}', { n: value(group.maximum) })
                  : p.best_names.join(', ')
              }
            />
            {rings && (
              <Figure
                label={t('Ringe pro gewertetem Schuss')}
                value={number(p.per_shot)}
                note={t('Nur innerhalb derselben Bedingungen vergleichbar')}
              />
            )}
            {!personal && (
              <Figure
                label={t('Mitgliederdurchschnitt')}
                value={value(p.member_average)}
                note={t('Jeder persönliche Durchschnitt zählt gleich')}
              />
            )}
            {personal && (
              <Figure
                label={t('Veränderung zum Vorjahr')}
                value={p.change == null ? '–' : `${p.change > 0 ? '+' : ''}${value(p.change)}`}
                note={
                  p.previous_average == null
                    ? t('Keine vergleichbaren Vorjahresergebnisse')
                    : t('Jüngstes Jahr gegenüber {year}', { year: p.previous_year ?? '' })
                }
              />
            )}
          </div>
        </section>
      )}
      {!group && data.group_summary.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Durchschnitt nach Wertungsbedingungen')}</h2>
          <p className="muted small">
            {t('Bedingungen auswählen, um Bestleistung und Verlauf zu sehen.')}
          </p>
          <DataTable
            label={t('Durchschnitt nach Wertungsbedingungen')}
            rows={data.group_summary}
            rowKey={(g) => g.id}
            columns={[
              {
                key: 'label',
                label: t('Wertungsbedingungen'),
                value: (g) => g.label,
                render: (g) => (
                  <button type="button" className="link-button" onClick={() => onGroup(g.id)}>
                    {g.label}
                  </button>
                ),
              },
              { key: 'count', label: t('Ergebnisse'), value: (g) => g.count, numeric: true },
              {
                key: 'average',
                label: t('Durchschnitt'),
                value: (g) => g.average,
                numeric: true,
                render: (g) => `${number(g.average)} ${g.unit_label}`,
              },
              {
                key: 'best',
                label: t('Bestleistung'),
                value: (g) => g.best,
                numeric: true,
                render: (g) => `${number(g.best)} ${g.unit_label}`,
              },
            ]}
          />
        </div>
      )}
      {s.starts === 0 && (
        <div className="card card-wide empty-state">
          <h2>{t('Noch keine Statistik für diese Auswahl')}</h2>
          <p className="muted">
            {t(
              'Andere Filter wählen oder einen Wettbewerb endgültig abschließen. Fehlende Ergebnisse werden nicht als null gerechnet.',
            )}
          </p>
        </div>
      )}
      {data.buckets.length > 0 && (
        <div className="competition-statistics-charts">
          <ChartCard
            title={t('Teilnahmen im Zeitverlauf')}
            note={t('Je Person und Wettbewerb einmal, auch bei mehreren Wertungen.')}
          >
            <TimeChart
              title={t('Teilnahmen im Zeitverlauf')}
              kind="bar"
              labels={data.buckets.map((b) => String(b.year))}
              format={(n) => number(n, 0)}
              series={[
                {
                  key: 'starts',
                  name: t('Teilnahmen'),
                  color: PRIMARY,
                  values: data.buckets.map((b) => b.starts),
                },
              ]}
            />
          </ChartCard>
          {group && (
            <ChartCard
              title={
                rings
                  ? t('Durchschnittliche Ringe im Zeitverlauf')
                  : t('Ergebnisdurchschnitt im Zeitverlauf')
              }
              note={t('Gleiche Wertungsbedingungen · {unit}', { unit })}
            >
              <TimeChart
                title={t('Leistungsentwicklung')}
                kind="line"
                labels={data.buckets.map((b) => String(b.year))}
                format={(n) => value(n)}
                series={[
                  {
                    key: 'average',
                    name: t('Durchschnitt'),
                    color: PRIMARY,
                    values: data.buckets.map((b) => b.average),
                  },
                ]}
              />
            </ChartCard>
          )}
        </div>
      )}
      {!personal && data.members.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Mitglieder im Überblick')}</h2>
          <p className="muted small">
            {t('Ein Mitglied auswählen, um die persönliche Statistik zu öffnen.')}
          </p>
          <DataTable<StatisticsMember>
            label={t('Mitglieder im Überblick')}
            rows={data.members}
            rowKey={(m) => m.membership}
            initialSort={{ key: 'name' }}
            columns={[
              {
                key: 'name',
                label: t('Mitglied'),
                value: (m) => m.name,
                render: (m) => (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => onMember(m.membership)}
                  >
                    {m.name}
                  </button>
                ),
              },
              { key: 'starts', label: t('Teilnahmen'), value: (m) => m.starts, numeric: true },
              { key: 'wins', label: t('Siege'), value: (m) => m.wins, numeric: true },
              { key: 'podiums', label: t('Podestplätze'), value: (m) => m.podiums, numeric: true },
              {
                key: 'prizes',
                label: t('Pfänder'),
                value: (m) => m.prizes,
                numeric: true,
                optional: true,
              },
              ...(group
                ? [
                    {
                      key: 'average',
                      label: t('Durchschnitt'),
                      value: (m: StatisticsMember) => m.average,
                      numeric: true,
                      render: (m: StatisticsMember) => value(m.average),
                    },
                    {
                      key: 'count',
                      label: t('Ergebnisse'),
                      value: (m: StatisticsMember) => m.count,
                      numeric: true,
                      optional: true,
                    },
                  ]
                : []),
            ]}
          />
        </div>
      )}
      {data.awards.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Titel und Auszeichnungen')}</h2>
          <p className="muted small">{t('{n} bestätigte Auszeichnungen', { n: s.awards })}</p>
          <ul className="plain-list">
            {data.awards.map((a) => (
              <li key={a.id}>
                <strong>{a.title}</strong>
                {!personal && <> · {a.name}</>}
                <span className="muted"> · {a.competition_title || a.year}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {personal && data.results.length > 0 && (
        <div className="card card-wide">
          <h2>{t('Einzelergebnisse')}</h2>
          <DataTable<StatisticsResult>
            label={t('Einzelergebnisse')}
            rows={data.results}
            rowKey={(r) => `${r.competition}:${r.scoring_id ?? 'bird'}`}
            initialSort={{ key: 'date', dir: 'desc' }}
            columns={[
              {
                key: 'date',
                label: t('Datum'),
                value: (r) => r.date,
                render: (r) => formatDate(r.date),
              },
              {
                key: 'title',
                label: t('Wettbewerb'),
                value: (r) => r.title,
                render: (r) => (
                  <>
                    {!portal && data.can_open ? (
                      <Link to={`/wettbewerbe/${r.competition}/auswertung`}>{r.title}</Link>
                    ) : (
                      r.title
                    )}
                    <div className="muted small">{r.scoring || t('Vogelschießen')}</div>
                  </>
                ),
              },
              {
                key: 'value',
                label: t('Ergebnis'),
                value: (r) => r.value,
                render: (r) =>
                  r.form === 'vogel'
                    ? r.prizes?.join(', ') || t('Kein Pfand')
                    : r.value == null
                      ? t('Kein Ergebnis erfasst')
                      : `${number(r.value, 3)} ${r.unit_label}`,
                numeric: true,
              },
              {
                key: 'place',
                label: t('Platzierung'),
                value: (r) => r.place,
                render: (r) =>
                  r.place
                    ? r.field
                      ? t('Platz {place} von {n}', { place: r.place, n: r.field })
                      : t('Platz {n}', { n: r.place })
                    : '–',
                numeric: true,
              },
            ]}
          />
        </div>
      )}
      <details className="card card-wide competition-statistics-explanation">
        <summary>{t('Wie werden die Kennzahlen berechnet?')}</summary>
        <div className="stack small">
          <p>
            {t(
              'Teilnahmen zählen jede Person je Wettbewerb einmal. Siege und Podestplätze zählen je Einzelwertung; Mannschaftserfolge werden nicht als persönliche Siege gezählt. Das Starterfeld für Platzierungen umfasst auch Gäste.',
            )}
          </p>
          <p>
            {t(
              'Durchschnitte und Bestleistungen werden nur für dieselben hinterlegten Wertungsbedingungen berechnet. Ringe, Zehntel, Teiler, Scheiben und Schusszahlen bleiben getrennt. Ohne bekannte Disziplin oder Scheibe werden Wettbewerbe nicht automatisch zusammengefasst.',
            )}
          </p>
          <p>
            {t(
              'Der Ergebnisdurchschnitt gewichtet jedes gültige Ergebnis gleich. Der Mitgliederdurchschnitt gewichtet jeden persönlichen Durchschnitt gleich. Fehlende Werte sind keine null; ein tatsächlich erfasstes Ergebnis von null zählt mit.',
            )}
          </p>
          <p>
            {t(
              'Die Veränderung vergleicht das gewählte oder jüngste Jahr mit dessen direktem Vorjahr. Für Ringe ist ein größerer Wert besser, für Teiler ein kleinerer.',
            )}
          </p>
        </div>
      </details>
    </>
  )
}
