import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { historyApi, type Series } from '../../api/competitionHistory.ts'
import { PERM } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { Checkbox, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { WebSlugField } from '../../components/WebSlugField.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { TitlesList } from './TitlesList.tsx'

export function SeriesPage() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const canManage = org.permissions.includes(PERM.competitionsManage)
  const { data, error, reload } = useLoad(() => historyApi.series.archive(org.id, id), [org.id, id])
  const [series, setSeries] = useState<Series | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const s = series ?? {
    id: data.id,
    name: data.name,
    description: data.description,
    on_website: data.on_website ?? true,
    competition_count: data.years.length,
    web_slug: data.web_slug,
    web_slug_auto: data.web_slug_auto,
  }

  async function save(changes: Partial<Series>) {
    const saved = await historyApi.series.update(org.id, id, changes)
    setSeries(saved)
  }

  return (
    <section>
      <PageHeader title={data.name} />
      {data.description && <p>{data.description}</p>}
      {canManage && (
        <Checkbox
          label={t('Archiv auf der Webseite zeigen')}
          checked={s.on_website}
          onChange={(on) => void save({ on_website: on })}
        />
      )}
      {canManage && (
        <WebSlugField
          key={`${s.web_slug ?? ''}-${String(s.web_slug_auto)}`}
          slug={s.web_slug ?? ''}
          auto={s.web_slug_auto !== false}
          hint={t('Leer: aus dem Namen, z. B. /ergebnisse/reihe/vereinsmeister/.')}
          onSave={(web_slug) => save({ web_slug })}
        />
      )}
      <h2>{t('Sieger je Jahr')}</h2>
      {data.years.length === 0 && (
        <p className="muted">
          {t(
            'Noch keine Wettbewerbe in dieser Reihe. Die Reihe wählt ihr beim Wettbewerb unter „Einrichten“.',
          )}
        </p>
      )}
      {data.years.map((y) => (
        <div key={y.competition} className="card card-wide">
          <h3>
            <Link to={`/wettbewerbe/${y.competition}/auswertung`}>{y.title}</Link>{' '}
            <span className="muted">· {y.year}</span>
          </h3>
          {y.winners.map((w) => (
            <p key={w.scoring}>
              <strong>{w.scoring}:</strong>{' '}
              {w.podium.length === 0
                ? '–'
                : w.podium
                    .map((r) =>
                      [r.place ? `${r.place}.` : '', r.name, r.value_text && `(${r.value_text})`]
                        .filter(Boolean)
                        .join(' '),
                    )
                    .join(', ')}
            </p>
          ))}
        </div>
      ))}
      {data.records.length > 0 && (
        <>
          <h2>{t('Bestenliste')}</h2>
          <p className="muted small">
            {t(
              'Bester Wert aller Jahre je Wertung; verglichen werden nur Jahre mit gleichen Regeln.',
            )}
          </p>
          <ul className="plain-list">
            {data.records.map((r) => (
              <li key={`${r.scoring}-${r.counted_shots}`}>
                <strong>{r.scoring}:</strong> {r.value_text} {r.unit_label} · {r.name} ({r.year})
              </li>
            ))}
          </ul>
        </>
      )}
      {data.units.length > 0 && (
        <>
          <h2>{t('Untereinheiten im Vergleich')}</h2>
          <ul className="plain-list">
            {data.units.map((u) => (
              <li key={u.unit}>
                <strong>{u.name}:</strong>{' '}
                {u.years.map((y) => t('{year} Platz {place}', y)).join(', ')}
              </li>
            ))}
          </ul>
        </>
      )}
      <TitlesList
        org={org.id}
        grants={data.titles}
        canManage={canManage}
        defaults={{ series: id }}
        onChanged={reload}
        heading={t('Titel')}
      />
    </section>
  )
}
