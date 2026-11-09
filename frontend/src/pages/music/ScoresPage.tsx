import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'
import { formats, duration } from './scoreHelpers.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { CatalogueImportPanel } from './CatalogueImportPanel.tsx'
import { ScoreFoldersPanel } from './ScoreFoldersPanel.tsx'

type Row = { id: number; [key: string]: string | number | boolean | null }
type Field = {
  key: string
  label: string
  type?: string
  options?: [string, string][]
  optional?: boolean
}

export function ScoresPage() {
  const org = useActiveOrg(),
    base = `/api/orgs/${org.id}/music/`
  const [tab, setTab] = useState('arrangements'),
    [selected, setSelected] = useState<Row | 'new' | null>(null),
    [search, setSearch] = useState(''),
    [error, setError] = useState('')
  const load = useLoad(async () => {
    const [pieces, arrangements, parts, files, documents] = await Promise.all([
      api.get<Row[]>(base + 'pieces/'),
      api.get<Row[]>(base + 'arrangements/'),
      api.get<Row[]>(base + 'parts/'),
      api.get<Row[]>(base + 'score-documents/'),
      org.permissions.includes('docs.view')
        ? api.get<Row[]>(base + 'score-documents/documents/')
        : Promise.resolve([]),
    ])
    return { pieces, arrangements, parts, files, documents }
  }, [org.id])
  if (load.error)
    return (
      <>
        <PageHeader />
        <Alert kind="error">{load.error}</Alert>
      </>
    )
  if (!load.data)
    return (
      <>
        <PageHeader />
        <p>{t('Lädt …')}</p>
      </>
    )
  const d = load.data,
    canEdit = org.permissions.includes('scores.edit'),
    opts = (rows: Row[], key: string): [string, string][] =>
      rows.map((r) => [String(r.id), String(r[key])])
  const arrangementName = (id: unknown) => {
    const a = d.arrangements.find((r) => r.id === id)
    return `${d.pieces.find((p) => p.id === a?.piece)?.title || ''} · ${a?.name || ''}`
  }
  const arrOpts = d.arrangements.map(
    (a) => [String(a.id), arrangementName(a.id)] as [string, string],
  )
  const fields: Record<string, Field[]> = {
    pieces: [
      { key: 'title', label: t('Titel') },
      { key: 'composer', label: t('Komponist'), optional: true },
      { key: 'on_website', label: t('Im Repertoire auf der Webseite'), type: 'checkbox' },
    ],
    arrangements: [
      { key: 'piece', label: t('Stück'), options: opts(d.pieces, 'title') },
      { key: 'name', label: t('Ausgabe / Arrangement') },
      { key: 'arranger', label: t('Arrangeur'), optional: true },
      { key: 'publisher', label: t('Verlag'), optional: true },
      { key: 'duration_seconds', label: t('Dauer in Sekunden'), type: 'number' },
      { key: 'difficulty', label: t('Schwierigkeitsgrad'), optional: true },
      { key: 'ensemble', label: t('Besetzungsbeschreibung'), optional: true },
      { key: 'license_note', label: t('Lizenzhinweise'), type: 'textarea', optional: true },
      { key: 'active', label: t('Aktiv'), type: 'checkbox' },
    ],
    parts: [
      { key: 'arrangement', label: t('Arrangement'), options: arrOpts },
      { key: 'instrument', label: t('Instrument') },
      { key: 'register', label: t('Register / Stimme'), optional: true },
      {
        key: 'kind',
        label: t('Art'),
        options: [
          ['part', t('Einzelstimme')],
          ['score', t('Partitur')],
        ],
      },
      { key: 'paper_format', label: t('Format'), options: formats() },
      { key: 'required_players', label: t('Benötigte Musiker'), type: 'number' },
      { key: 'copies', label: t('Vorhandene Exemplare'), type: 'number' },
      { key: 'location', label: t('Lagerort'), optional: true },
    ],
    files: [
      { key: 'arrangement', label: t('Arrangement'), options: arrOpts },
      {
        key: 'part',
        label: t('Einzelstimme'),
        options: d.parts.map((p) => [
          String(p.id),
          `${arrangementName(p.arrangement)}: ${p.instrument} ${p.register}`,
        ]),
        optional: true,
      },
      { key: 'document', label: t('Dokument'), options: opts(d.documents, 'title') },
      { key: 'usage_note', label: t('Nutzungshinweise'), type: 'textarea', optional: true },
      { key: 'position', label: t('Reihenfolge bei mehreren Dateien'), type: 'number' },
      {
        key: 'notation_part',
        label: t('Stimme in der MusicXML-Partitur (leer: nach Instrument)'),
        optional: true,
      },
    ],
  }
  const rows = tab === 'folders' ? [] : d[tab as 'pieces' | 'arrangements' | 'parts' | 'files'],
    names = {
      pieces: t('Stücke'),
      arrangements: t('Arrangements'),
      parts: t('Stimmenbestand'),
      files: t('Notenunterlagen'),
      folders: t('Notenmappen'),
    }
  const visibleRows = rows.filter((r) =>
    [
      r.title,
      r.name,
      r.instrument,
      r.register,
      r.composer,
      r.arranger,
      arrangementName(r.arrangement),
    ]
      .join(' ')
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  )
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Notenbestand')}
        description={t(
          'Stücke, Arrangements, Stimmen und digitale Notenunterlagen an einem Ort verwalten.',
        )}
      />
      <nav className="tabs" aria-label={t('Ansichten')}>
        {Object.entries(names).map(([key, label]) => (
          <button
            className={`tab${tab === key ? ' active' : ''}`}
            aria-current={tab === key ? 'page' : undefined}
            key={key}
            onClick={async () => {
              if (await confirmLeave()) {
                setTab(key)
                setSelected(null)
              }
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <p>
        {t(
          'Digitale Noten werden in der Dokumentenablage gespeichert. Deren Freigaben gelten weiterhin; Lizenzhinweise ersetzen keine Nutzungsrechte.',
        )}
      </p>
      <Link to="/dokumente">{t('Zur Dokumentenablage')}</Link>
      {canEdit && (
        <details>
          <summary>{t('Notenkatalog importieren')}</summary>
          <CatalogueImportPanel onSaved={load.reload} />
        </details>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {tab === 'folders' && (
        <ScoreFoldersPanel
          base={base}
          arrangements={arrOpts}
          canEdit={canEdit}
          live={org.modules.includes('music')}
        />
      )}
      {tab !== 'folders' && (
        <>
          <div className="music-toolbar">
            <label>
              {t('Noten suchen')}
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} />
            </label>
            {canEdit && (
              <button
                className="button button-primary"
                onClick={async () => {
                  if (await confirmLeave()) setSelected('new')
                }}
              >
                {t('Anlegen')}
              </button>
            )}
          </div>
          {canEdit && selected && (
            <ScoreForm
              key={`${tab}-${selected === 'new' ? 'new' : selected.id}`}
              fields={fields[tab]}
              initial={selected === 'new' ? undefined : selected}
              onClose={() => setSelected(null)}
              onSave={async (values) => {
                const endpoint = tab === 'files' ? 'score-documents' : tab
                const target = base + endpoint + '/'
                if (selected === 'new') await api.post(target, values)
                else await api.patch(`${target}${selected.id}/`, values)
                setSelected(null)
                await load.reload()
              }}
            />
          )}
          {!visibleRows.length && (
            <MusicEmptyState>
              {search.trim()
                ? t('Keine passenden Einträge gefunden.')
                : t('Noch keine Einträge vorhanden.')}
            </MusicEmptyState>
          )}
          {visibleRows.map((r) => (
            <article key={r.id} className="card stack music-record">
              <strong>{String(r.title || r.name || r.instrument)}</strong>
              {tab === 'pieces' && (
                <p>
                  {r.composer}
                  {r.on_website ? ` · ${t('im Repertoire auf der Webseite')}` : ''}
                </p>
              )}
              {tab === 'arrangements' && (
                <>
                  <p>
                    {d.pieces.find((p) => p.id === r.piece)?.title} · {r.arranger} · {r.publisher} ·{' '}
                    {duration(Number(r.duration_seconds))} · {r.difficulty} · {r.ensemble}
                  </p>
                  <p>{r.license_note}</p>
                  <p>{r.active ? t('Aktiv') : t('Archiviert')}</p>
                </>
              )}
              {tab === 'parts' && (
                <p>
                  {arrangementName(r.arrangement)} · {r.register} ·{' '}
                  {r.kind === 'score' ? t('Partitur') : t('Einzelstimme')} ·{' '}
                  {formats().find((f) => f[0] === r.paper_format)?.[1]} ·{' '}
                  {t('Vorhandene Exemplare')}: {r.copies} · {t('Benötigte Musiker')}:{' '}
                  {r.required_players} · {r.location}
                </p>
              )}
              {tab === 'files' && (
                <>
                  <p>
                    {arrangementName(r.arrangement)} · {r.usage_note}
                  </p>
                  <a href={`${base}score-documents/${r.id}/download/`}>
                    {t('Notenunterlage öffnen')}
                  </a>
                </>
              )}
              {canEdit && (
                <div className="actions">
                  <button
                    className="button button-ghost"
                    onClick={async () => {
                      if (await confirmLeave()) setSelected(r)
                    }}
                  >
                    {t('Bearbeiten')}
                  </button>
                  {['parts', 'files'].includes(tab) && (
                    <button
                      className="button button-ghost"
                      onClick={async () => {
                        if (!(await confirmDialog(t('Eintrag entfernen?')))) return
                        try {
                          await api.del(
                            `${base}${tab === 'files' ? 'score-documents' : tab}/${r.id}/`,
                          )
                          await load.reload()
                        } catch (e) {
                          setError(errorMessage(e))
                        }
                      }}
                    >
                      {t('Entfernen')}
                    </button>
                  )}
                </div>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  )
}

export function ScoreForm({
  fields,
  initial,
  onSave,
  onClose,
}: {
  fields: Field[]
  initial?: Row
  onSave: (v: Record<string, unknown>) => Promise<void>
  onClose?: () => void
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() =>
      Object.fromEntries(
        fields.map((f) => [
          f.key,
          initial?.[f.key] ??
            (f.type === 'checkbox'
              ? true
              : f.type === 'number'
                ? f.optional
                  ? ''
                  : 0
                : f.optional
                  ? ''
                  : f.options?.[0]?.[0] || ''),
        ]),
      ),
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [clean] = useState(JSON.stringify(values))
  useDraftGuard(JSON.stringify(values) !== clean)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(
            Object.fromEntries(
              fields.map((f) => [
                f.key,
                values[f.key] === '' && f.optional && f.options ? null : values[f.key],
              ]),
            ),
          )
        } catch (e) {
          setError(errorMessage(e))
        } finally {
          setBusy(false)
        }
      }}
    >
      {error && <Alert kind="error">{error}</Alert>}
      <div className="music-form-fields">
        {fields.map((f) => (
          <label key={f.key} className={f.type === 'textarea' ? 'music-field-wide' : undefined}>
            {f.label}
            {f.options ? (
              <select
                required={!f.optional}
                value={String(values[f.key] ?? '')}
                onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
              >
                {f.optional && <option value="">—</option>}
                {f.options.map(([v, l]) => (
                  <option value={v} key={v}>
                    {l}
                  </option>
                ))}
              </select>
            ) : f.type === 'textarea' ? (
              <textarea
                maxLength={2000}
                value={String(values[f.key])}
                onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
              />
            ) : (
              <input
                required={!f.optional && f.type !== 'checkbox'}
                type={f.type || 'text'}
                min={f.type === 'number' ? 0 : undefined}
                value={f.type === 'checkbox' ? undefined : String(values[f.key] ?? '')}
                checked={f.type === 'checkbox' ? Boolean(values[f.key]) : undefined}
                onChange={(e) =>
                  setValues({
                    ...values,
                    [f.key]: f.type === 'checkbox' ? e.target.checked : e.target.value,
                  })
                }
              />
            )}
          </label>
        ))}
      </div>
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        {onClose && (
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => {
              if (await confirmLeave()) onClose()
            }}
          >
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}
