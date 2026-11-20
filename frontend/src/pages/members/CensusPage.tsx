// Stichtagsstatistik: Mitglieder an einem Tag nach Alter, Geschlecht, Wohnort und Abteilung,
// als PDF, Excel oder CSV für Sportbund, Verband und Zuschussanträge (Lückenliste 20.11. B2).
import { useState } from 'react'
import { censusApi } from '../../api/statistics.ts'
import type { CensusAgeRow, CensusQuery, CensusStats } from '../../api/statistics.ts'
import { formatDate, useQueryLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'

const count = (n: number) => n.toLocaleString(locale())

function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function MemberCensus({
  base,
  scope,
  note,
}: {
  /** Adresse der Auswertung (``censusBase``) */
  base: string
  /** Kennung der Sicht für das Neuladen */
  scope: string
  note?: string
}) {
  const [day, setDay] = useState(today)
  const [scheme, setScheme] = useState('sport')
  const [counting, setCounting] = useState<'stichtag' | 'jahrgang'>('stichtag')
  // null = alle Mitgliedsarten
  const [types, setTypes] = useState<number[] | null>(null)
  const query: CensusQuery = {
    stichtag: day || undefined,
    alter: scheme,
    zaehlung: counting,
    arten: types ?? undefined,
  }
  const key = JSON.stringify(query)
  const { data, error, reload } = useQueryLoad(() => censusApi.load(base, query), [scope, key])

  const toggleType = (id: number, all: number[]) => {
    const current = types ?? all
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    // Mindestens eine Art bleibt gewählt; alle gewählt = keine Einschränkung
    if (next.length === 0) return
    setTypes(next.length === all.length ? null : next)
  }

  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Mitglieder an einem Stichtag nach Alter, Geschlecht, Wohnort und Gruppe, etwa für die Bestandserhebung des Sportbunds, den Verband oder einen Zuschussantrag.',
        )}
      </p>
      <div className="card card-wide filters">
        <label>
          {t('Stichtag')}{' '}
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} required />
        </label>
        <label>
          {t('Altersgruppen')}{' '}
          <select value={scheme} onChange={(e) => setScheme(e.target.value)}>
            {(
              data?.schemes ?? [
                { key: 'sport', label: t('Sportbund') },
                { key: 'jugend', label: t('Jugendförderung') },
                { key: 'zehn', label: t('Zehnjahresgruppen') },
              ]
            ).map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Alter')}{' '}
          <select
            value={counting}
            onChange={(e) => setCounting(e.target.value === 'jahrgang' ? 'jahrgang' : 'stichtag')}
          >
            <option value="stichtag">{t('am Stichtag vollendet')}</option>
            <option value="jahrgang">{t('nach Jahrgang (Jahr minus Geburtsjahr)')}</option>
          </select>
        </label>
        {data && (
          <span className="button-row push-right">
            <a
              className="button button-ghost"
              href={censusApi.fileUrl(base, query, 'pdf')}
              target="_blank"
              rel="noreferrer"
            >
              {t('PDF')}
            </a>
            <a className="button button-ghost" href={censusApi.fileUrl(base, query, 'xlsx')}>
              {t('Excel')}
            </a>
            <a className="button button-ghost" href={censusApi.fileUrl(base, query, 'csv')}>
              {t('CSV')}
            </a>
          </span>
        )}
      </div>
      {data && data.types.length > 1 && (
        <fieldset className="card card-wide">
          <legend>{t('Mitgliedsarten')}</legend>
          <div className="checkbox-grid">
            {data.types.map((ty) => {
              const all = data.types.map((x) => x.id)
              return (
                <label key={ty.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={types === null || types.includes(ty.id)}
                    onChange={() => toggleType(ty.id, all)}
                  />{' '}
                  {ty.name} ({count(ty.count)})
                </label>
              )
            })}
          </div>
        </fieldset>
      )}
      {note && <p className="muted small">{note}</p>}
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!data && !error && (
        <p className="muted" role="status">
          {t('Wird geladen …')}
        </p>
      )}
      {data && <CensusTables data={data} />}
    </div>
  )
}

function AgeTable({
  data,
  rows,
  genders,
  total,
  caption,
}: {
  data: CensusStats
  rows: CensusAgeRow[]
  genders: number[]
  total: number
  caption: string
}) {
  return (
    <div className="table-scroll">
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{t('Altersgruppe')}</th>
            {data.gender_labels.map((g) => (
              <th key={g} scope="col" className="num">
                {g}
              </th>
            ))}
            <th scope="col" className="num">
              {t('gesamt')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows
            .filter((r, i) => i < data.age_groups.length || r.total > 0)
            .map((r) => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                {r.counts.map((c, i) => (
                  <td key={i} className="num">
                    {count(c)}
                  </td>
                ))}
                <td className="num">
                  <strong>{count(r.total)}</strong>
                </td>
              </tr>
            ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">{t('Summe')}</th>
            {genders.map((c, i) => (
              <td key={i} className="num">
                <strong>{count(c)}</strong>
              </td>
            ))}
            <td className="num">
              <strong>{count(total)}</strong>
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function CensusTables({ data }: { data: CensusStats }) {
  if (data.total === 0)
    return (
      <div className="card empty-state">
        <p>{t('Am {date} gibt es keine Mitglieder.', { date: formatDate(data.stichtag) })}</p>
      </div>
    )
  return (
    <>
      <div className="tiles tiles-figures">
        <div className="card tile">
          <h2>
            {t('Mitglieder am')} {formatDate(data.stichtag)}
          </h2>
          <p className="amount-big">{count(data.total)}</p>
          <p className="small muted">{t('Bestand nach den Austritten dieses Tages')}</p>
        </div>
        <div className="card tile">
          <h2>{t('Personen')}</h2>
          <p className="amount-big">{count(data.persons)}</p>
        </div>
        {data.organizations > 0 && (
          <div className="card tile">
            <h2>{t('Organisationen')}</h2>
            <p className="amount-big">{count(data.organizations)}</p>
            <p className="small muted">{t('ohne Alter und Geschlecht')}</p>
          </div>
        )}
      </div>

      <section className="card card-wide">
        <h2>{t('Alter und Geschlecht')}</h2>
        <AgeTable
          data={data}
          rows={data.rows}
          genders={data.genders}
          total={data.persons}
          caption={t('Alter und Geschlecht')}
        />
      </section>

      {data.places.length > 0 && (
        <section className="card card-wide">
          <h2>{t('Wohnorte')}</h2>
          <p className="muted small">
            {t('Ort aus der Anschrift; die Altersgruppen je Ort stehen in der Excel-Datei.')}
          </p>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t('Ort')}</th>
                  <th scope="col">{t('PLZ')}</th>
                  {data.gender_labels.map((g) => (
                    <th key={g} scope="col" className="num">
                      {g}
                    </th>
                  ))}
                  <th scope="col" className="num">
                    {t('gesamt')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.places.map((p) => (
                  <tr key={p.city}>
                    <th scope="row" className={p.missing ? 'muted' : undefined}>
                      {p.city}
                    </th>
                    <td>{p.postal_codes.join(', ')}</td>
                    {p.genders.map((c, i) => (
                      <td key={i} className="num">
                        {count(c)}
                      </td>
                    ))}
                    <td className="num">
                      <strong>{count(p.total)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.groups.map((g) => (
        <section key={g.id} className="card card-wide">
          <h2>
            {data.groups_title}: {g.name}
          </h2>
          <AgeTable
            data={data}
            rows={g.rows}
            genders={g.genders}
            total={g.total}
            caption={g.name}
          />
        </section>
      ))}
      {data.groups.length > 0 && (
        <p className="muted small">
          {t('Wer mehreren Gruppen ({title}) angehört, zählt in jeder.', {
            title: data.groups_title,
          })}
        </p>
      )}
    </>
  )
}
