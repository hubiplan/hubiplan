import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

type Musician = { id: number; membership: number | null; active: boolean }
type Skill = {
  id: number
  musician: number
  instrument: string
  register: string
  primary: boolean
}

/** Kurzprofil im Reiter „Musik“ der Mitgliedsakte; bearbeitet wird im Musikbereich. */
export function MusicTab({ orgId, memberId }: { orgId: number; memberId: number }) {
  const base = `/api/orgs/${orgId}/music/`
  const { data, error } = useLoad(async () => {
    const musicians = await api.get<Musician[]>(`${base}musicians/`)
    const musician = musicians.find((m) => m.membership === memberId) ?? null
    const skills = musician
      ? (await api.get<Skill[]>(`${base}skills/`)).filter((s) => s.musician === musician.id)
      : []
    return { musician, skills }
  }, [orgId, memberId])

  return (
    <section className="card card-wide" aria-labelledby="musik-titel">
      <h2 id="musik-titel">{t('Musikerprofil')}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      {!data && !error && <Loading />}
      {data && !data.musician && <p className="muted">{t('Noch kein Musikerprofil angelegt.')}</p>}
      {data?.musician && (
        <>
          <p>{data.musician.active ? t('Aktiv') : t('Nicht aktiv')}</p>
          {data.skills.length === 0 ? (
            <p className="muted">{t('Noch keine Instrumente eingetragen.')}</p>
          ) : (
            <ul className="plain-list">
              {[...data.skills]
                .sort((a, b) => Number(b.primary) - Number(a.primary))
                .map((s) => (
                  <li key={s.id}>
                    <strong>{s.instrument}</strong>
                    {s.register && ` · ${s.register}`}
                    {s.primary && <span className="muted small">{t(' (Hauptinstrument)')}</span>}
                  </li>
                ))}
            </ul>
          )}
        </>
      )}
      <p>
        <Link to={`/musik/musiker?mitglied=${memberId}`}>{t('Im Musikbereich öffnen')}</Link>
      </p>
    </section>
  )
}
