import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ScoreForm } from './ScoresPage.tsx'
import { formats, duration } from './scoreHelpers.ts'

type Entry = {
  id: number
  position: number
  kind: string
  arrangement: number | null
  title: string
  arrangement_name: string
  duration_seconds: number | null
  effective_seconds: number
  paper_format: string
  note: string
}
type Program = {
  entries: Entry[]
  total_seconds: number
  regular_seconds: number
  encore_seconds: number
  preparation: {
    arrangement: number
    name: string
    title: string
    paper_format: string
    active: boolean
    missing_specification: boolean
    license_note: string
    voices: {
      instrument: string
      register: string
      kind: string
      planned: number
      accepted: number
      required: number
      missing_players: number
      missing_planned: number
      needed_copies: number
      copies: number
      loaned?: number
      available?: number
      held?: number
      missing_copies: number
      locations: string[]
    }[]
  }[]
}

export function ProgramPanel({ performance }: { performance: number }) {
  const org = useActiveOrg(),
    base = `/api/orgs/${org.id}/music/`,
    url = `${base}performances/${performance}/program/`
  const load = useLoad(async () => {
    const [program, arrangements, event] = await Promise.all([
      api.get<Program>(url),
      api.get<{ id: number; name: string; active: boolean }[]>(base + 'arrangements/'),
      api.get<{ title: string; event: number }>(`${base}performances/${performance}/`),
    ])
    return { program, arrangements, event }
  }, [org.id, performance])
  const [editing, setEditing] = useState<Entry | 'new' | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return <p>{t('Lädt …')}</p>
  const { program: p, arrangements, event } = load.data,
    canEdit = org.permissions.includes('music.edit')
  async function act(data: Record<string, unknown>) {
    setBusy(true)
    setError('')
    try {
      await api.post(url, data)
      await load.reload()
    } catch (e) {
      setError(errorMessage(e))
      throw e
    } finally {
      setBusy(false)
    }
  }
  const move = async (index: number, delta: number) => {
    if (!(await confirmLeave())) return
    const ids = p.entries.map((e) => e.id)
    ;[ids[index], ids[index + delta]] = [ids[index + delta], ids[index]]
    await act({ action: 'reorder', ids })
  }
  return (
    <section className="stack">
      <Link to="/musik">{t('Zurück')}</Link>
      <h1>
        {t('Musikalisches Programm')}: {event.title}
      </h1>
      {error && <Alert kind="error">{error}</Alert>}
      <p>
        {t('Programmdauer')}: {duration(p.regular_seconds)} · {t('Zugaben')}:{' '}
        {duration(p.encore_seconds)} · {t('Gesamtdauer')}: {duration(p.total_seconds)}
      </p>
      <div className="actions">
        <a className="button button-ghost" href={url + '?export=program'}>
          {t('Programmliste herunterladen')}
        </a>
        <a className="button button-ghost" href={url + '?export=parts'}>
          {t('Stimmenliste herunterladen')}
        </a>
        <Link to={`/aufgaben?termin=${event.event}`}>{t('Aufgaben für Notenvorbereitung')}</Link>
        <Link to="/musik?noten=1">{t('Zum Notenbestand')}</Link>
      </div>
      {canEdit && (
        <button
          className="button button-primary"
          onClick={async () => {
            if (await confirmLeave()) setEditing('new')
          }}
        >
          {t('Programmpunkt hinzufügen')}
        </button>
      )}
      {editing && canEdit && (
        <ScoreForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          fields={[
            {
              key: 'kind',
              label: t('Art'),
              options: [
                ['piece', t('Stück')],
                ['pause', t('Pause')],
                ['encore', t('Zugabe')],
              ],
            },
            {
              key: 'arrangement',
              label: t('Arrangement'),
              options: arrangements
                .filter(
                  (a) => a.active || a.id === (editing === 'new' ? null : editing.arrangement),
                )
                .map((a) => [String(a.id), a.name]),
              optional: true,
            },
            {
              key: 'duration_seconds',
              label: t('Dauer in Sekunden'),
              type: 'number',
              optional: true,
            },
            { key: 'paper_format', label: t('Format'), options: formats() },
            { key: 'note', label: t('Hinweis'), optional: true },
          ]}
          onClose={() => setEditing(null)}
          onSave={async (values) => {
            await act({
              ...values,
              action: 'save',
              ...(editing === 'new' ? {} : { id: editing.id }),
              duration_seconds:
                values.duration_seconds === '' ? null : Number(values.duration_seconds),
            })
            setEditing(null)
          }}
        />
      )}
      {p.entries.map((e, i) => (
        <article key={e.id} className="card stack">
          <strong>
            {e.position}. {e.kind === 'pause' ? t('Pause') : e.title}{' '}
            {e.kind === 'encore' ? `(${t('Zugabe')})` : ''}
          </strong>
          <p>
            {e.arrangement_name} · {duration(e.effective_seconds)} · {e.note}
          </p>
          {e.effective_seconds === 0 && <p>{t('Dauer noch nicht angegeben.')}</p>}
          {canEdit && (
            <div className="actions">
              <button
                className="button button-ghost"
                disabled={busy || i === 0}
                onClick={() => void move(i, -1).catch(() => {})}
              >
                {t('Nach oben')}
              </button>
              <button
                className="button button-ghost"
                disabled={busy || i === p.entries.length - 1}
                onClick={() => void move(i, 1).catch(() => {})}
              >
                {t('Nach unten')}
              </button>
              <button
                className="button button-ghost"
                onClick={async () => {
                  if (await confirmLeave()) setEditing(e)
                }}
              >
                {t('Bearbeiten')}
              </button>
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  if (await confirmDialog(t('Eintrag entfernen?')))
                    void act({ action: 'delete', id: e.id }).catch(() => {})
                }}
              >
                {t('Entfernen')}
              </button>
            </div>
          )}
        </article>
      ))}
      <h2>{t('Besetzung und Notenvorbereitung')}</h2>
      <p>
        {t(
          'Instrument und Stimme werden anhand ihrer Bezeichnung verglichen. Bestände und Lizenzen vor der Ausgabe prüfen.',
        )}
      </p>
      {p.preparation.map((a) => (
        <article key={`${a.arrangement}-${a.paper_format}`} className="card stack">
          <h3>
            {a.title} · {a.name} · {formats().find((f) => f[0] === a.paper_format)?.[1]}
          </h3>
          {(!a.active || a.missing_specification) && (
            <Alert kind="error">
              {!a.active ? t('Arrangement ist archiviert.') : t('Besetzungsangaben fehlen.')}
            </Alert>
          )}
          <p>{a.license_note}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {[
                    t('Instrument'),
                    t('Register / Stimme'),
                    t('Benötigte Musiker'),
                    t('Geplant'),
                    t('Zugesagt'),
                    t('Fehlende Musiker'),
                    t('Benötigte Exemplare'),
                    t('Vorhandene Exemplare'),
                    t('Ausgegeben'),
                    t('Freie Exemplare'),
                    t('Bei Eingeteilten'),
                    t('Fehlende Exemplare'),
                    t('Lagerort'),
                  ].map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.voices.map((v, i) => (
                  <tr key={i}>
                    <td>{v.kind === 'score' ? t('Partitur') : v.instrument}</td>
                    <td>{v.register}</td>
                    <td>{v.kind === 'score' ? '—' : v.required}</td>
                    <td>{v.planned}</td>
                    <td>{v.accepted}</td>
                    <td>{v.missing_players}</td>
                    <td>{v.needed_copies}</td>
                    <td>{v.copies}</td>
                    <td>{v.loaned || 0}</td>
                    <td>{v.available ?? v.copies}</td>
                    <td>{v.held || 0}</td>
                    <td>{v.missing_copies}</td>
                    <td>{v.locations.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ))}
    </section>
  )
}
