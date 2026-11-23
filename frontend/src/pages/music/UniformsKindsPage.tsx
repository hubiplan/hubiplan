import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { MusicEmptyState, MusicHeader } from './MusicLayout.tsx'

export type Uniform = {
  id: number
  name: string
  description: string
  checklist: string[]
  has_image: boolean
  active: boolean
}
export type PerformanceKind = {
  id: number
  name: string
  formation: string
  uniform: number | null
  on_website: boolean
  active: boolean
}

export const formationOptions: [string, string][] = [
  ['seated', t('Sitzend')],
  ['standing', t('Stehend')],
  ['march', t('Umzug')],
]

/** Uniformen und Auftrittsarten der Einheit (Issues #712 und #713), /musik/uniformen */
export function UniformsKindsPage() {
  const org = useActiveOrg()
  const base = `/api/orgs/${org.id}/music/`
  const load = useLoad(async () => {
    const [uniforms, kinds] = await Promise.all([
      api.get<Uniform[]>(`${base}uniforms/`),
      api.get<PerformanceKind[]>(`${base}performance-kinds/`),
    ])
    return { uniforms, kinds }
  }, [org.id])
  const [error, setError] = useState('')
  const [editUniform, setEditUniform] = useState<Uniform | 'new' | null>(null)
  const [editKind, setEditKind] = useState<PerformanceKind | 'new' | null>(null)
  const [version, setVersion] = useState(0)
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
        <Loading />
      </>
    )
  const { uniforms, kinds } = load.data
  const canEdit = org.permissions.includes('music.edit')
  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      await load.reload()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    }
  }
  const remove = async (kind: 'uniforms' | 'performance-kinds', id: number) => {
    if (
      await confirmDialog({
        final: true,
        message: t('Eintrag entfernen?'),
        confirmLabel: t('Entfernen'),
      })
    )
      await act(() => api.del(`${base}${kind}/${id}/`))
  }
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Uniformen und Auftrittsarten')}
        description={t(
          'Feste Auswahl für eure Auftritte. Wer eingeteilt ist, sieht die Uniform samt Checkliste im Mitgliederbereich.',
        )}
      />
      {error && <Alert kind="error">{error}</Alert>}

      <h2>{t('Uniformen')}</h2>
      {canEdit && !editUniform && (
        <button className="button button-primary" onClick={() => setEditUniform('new')}>
          {t('Uniform anlegen')}
        </button>
      )}
      {canEdit && editUniform && (
        <UniformForm
          key={editUniform === 'new' ? 'new' : editUniform.id}
          initial={editUniform === 'new' ? undefined : editUniform}
          onCancel={() => setEditUniform(null)}
          onSave={async (values) => {
            if (
              await act(() =>
                editUniform === 'new'
                  ? api.post(`${base}uniforms/`, values)
                  : api.patch(`${base}uniforms/${editUniform.id}/`, values),
              )
            )
              setEditUniform(null)
          }}
        />
      )}
      {!uniforms.length && <MusicEmptyState>{t('Noch keine Uniformen.')}</MusicEmptyState>}
      {uniforms.map((u) => (
        <article className="card stack music-record" key={u.id}>
          <strong>
            {u.name}
            {!u.active && ` · ${t('Archiviert')}`}
          </strong>
          {u.has_image && (
            <img
              className="music-uniform-image"
              src={`${base}uniforms/${u.id}/image/?v=${version}`}
              alt={u.name}
            />
          )}
          {!!u.description && <p>{u.description}</p>}
          {!!u.checklist.length && (
            <ul className="music-checklist">
              {u.checklist.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          )}
          {canEdit && (
            <div className="music-record-actions">
              <button className="button button-ghost" onClick={() => setEditUniform(u)}>
                {t('Bearbeiten')}
              </button>
              <label className="button button-ghost">
                {u.has_image ? t('Bild ersetzen') : t('Bild hinzufügen')}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  hidden
                  onChange={async (e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (!file) return
                    const form = new FormData()
                    form.append('file', file)
                    await act(() => api.post(`${base}uniforms/${u.id}/image/`, form))
                    setVersion((v) => v + 1)
                  }}
                />
              </label>
              {u.has_image && (
                <button
                  className="button button-ghost"
                  onClick={() => act(() => api.del(`${base}uniforms/${u.id}/image/`))}
                >
                  {t('Bild entfernen')}
                </button>
              )}
              <button
                className="button button-ghost"
                onClick={() =>
                  act(() => api.patch(`${base}uniforms/${u.id}/`, { active: !u.active }))
                }
              >
                {u.active ? t('Archivieren') : t('Wieder aktivieren')}
              </button>
              <button className="button button-ghost" onClick={() => remove('uniforms', u.id)}>
                {t('Entfernen')}
              </button>
            </div>
          )}
        </article>
      ))}

      <h2>{t('Auftrittsarten')}</h2>
      <p className="muted">
        {t('Spielform und Uniform einer Art werden beim Wählen der Art am Auftritt vorgeschlagen.')}
      </p>
      {canEdit && !editKind && (
        <button className="button button-primary" onClick={() => setEditKind('new')}>
          {t('Auftrittsart anlegen')}
        </button>
      )}
      {canEdit && editKind && (
        <KindForm
          key={editKind === 'new' ? 'new' : editKind.id}
          initial={editKind === 'new' ? undefined : editKind}
          uniforms={uniforms}
          onCancel={() => setEditKind(null)}
          onSave={async (values) => {
            if (
              await act(() =>
                editKind === 'new'
                  ? api.post(`${base}performance-kinds/`, values)
                  : api.patch(`${base}performance-kinds/${editKind.id}/`, values),
              )
            )
              setEditKind(null)
          }}
        />
      )}
      {!kinds.length && <MusicEmptyState>{t('Noch keine Auftrittsarten.')}</MusicEmptyState>}
      {kinds.map((k) => (
        <article className="card stack music-record" key={k.id}>
          <strong>
            {k.name}
            {!k.active && ` · ${t('Archiviert')}`}
          </strong>
          <p>
            {[
              k.formation
                ? `${t('Spielform')}: ${formationOptions.find((f) => f[0] === k.formation)?.[1]}`
                : '',
              k.uniform
                ? `${t('Uniform')}: ${uniforms.find((u) => u.id === k.uniform)?.name || ''}`
                : '',
              k.on_website ? t('Auf der Webseite genannt') : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          {canEdit && (
            <div className="music-record-actions">
              <button className="button button-ghost" onClick={() => setEditKind(k)}>
                {t('Bearbeiten')}
              </button>
              <button
                className="button button-ghost"
                onClick={() =>
                  act(() => api.patch(`${base}performance-kinds/${k.id}/`, { active: !k.active }))
                }
              >
                {k.active ? t('Archivieren') : t('Wieder aktivieren')}
              </button>
              <button
                className="button button-ghost"
                onClick={() => remove('performance-kinds', k.id)}
              >
                {t('Entfernen')}
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  )
}

function UniformForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Uniform
  onSave: (values: Record<string, unknown>) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [checklist, setChecklist] = useState((initial?.checklist || []).join('\n'))
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave({
            name,
            description,
            checklist: checklist
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean),
          })
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="music-form-fields">
        <label>
          {t('Name')}
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="music-field-wide">
          {t('Beschreibung')}
          <textarea
            maxLength={1000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="music-field-wide">
          {t('Was dazugehört (eine Zeile je Punkt)')}
          <textarea value={checklist} onChange={(e) => setChecklist(e.target.value)} />
        </label>
      </div>
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button className="button button-ghost" type="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function KindForm({
  initial,
  uniforms,
  onSave,
  onCancel,
}: {
  initial?: PerformanceKind
  uniforms: Uniform[]
  onSave: (values: Record<string, unknown>) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name || '')
  const [formation, setFormation] = useState(initial?.formation || '')
  const [uniform, setUniform] = useState(initial?.uniform ? String(initial.uniform) : '')
  const [onWebsite, setOnWebsite] = useState(initial?.on_website || false)
  const [busy, setBusy] = useState(false)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave({
            name,
            formation,
            uniform: uniform ? Number(uniform) : null,
            on_website: onWebsite,
          })
        } finally {
          setBusy(false)
        }
      }}
    >
      <div className="music-form-fields">
        <label>
          {t('Name')}
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          {t('Vorschlag Spielform')}
          <select value={formation} onChange={(e) => setFormation(e.target.value)}>
            <option value="">—</option>
            {formationOptions.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Vorschlag Uniform')}
          <select value={uniform} onChange={(e) => setUniform(e.target.value)}>
            <option value="">—</option>
            {uniforms
              .filter((u) => u.active || String(u.id) === uniform)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={onWebsite}
            onChange={(e) => setOnWebsite(e.target.checked)}
          />
          {t('Art auf der Webseite beim Termin nennen')}
        </label>
      </div>
      <div className="actions">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button className="button button-ghost" type="button" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
