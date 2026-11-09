import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

type Leader = { id: number; musician: number; name: string }
type Musician = { id: number; display_name: string; active?: boolean }

/** Wer in der App allen Geräten das nächste Stück vorgeben darf (Dirigent, Stabführer …). */
export function LeadersPanel({
  base,
  target,
  canEdit,
  heading = true,
}: {
  heading?: boolean
  base: string
  target: { folder: number } | { performance: number } | { rehearsal: number }
  canEdit: boolean
}) {
  const [key, id] = Object.entries(target)[0] as [string, number]
  const [choice, setChoice] = useState(''),
    [error, setError] = useState('')
  const load = useLoad(async () => {
    const [leaders, musicians] = await Promise.all([
      api.get<Leader[]>(`${base}leaders/?${key}=${id}`),
      canEdit ? api.get<Musician[]>(base + 'musicians/').catch(() => []) : Promise.resolve([]),
    ])
    return { leaders, musicians }
  }, [base, key, id, canEdit])
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!load.data) return null
  const { leaders, musicians } = load.data
  const taken = new Set(leaders.map((l) => l.musician))
  const free = musicians.filter((m) => m.active !== false && !taken.has(m.id))
  const run = async (action: () => Promise<unknown>) => {
    setError('')
    try {
      await action()
      await load.reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <div className="stack">
      {heading ? <h2>{t('Leitung in der App')}</h2> : <strong>{t('Leitung in der App')}</strong>}
      <p>
        {t(
          'Die Leitung (z. B. Dirigent oder Stabführer) kann in der App allen Geräten das nächste Stück vorgeben. Wer Musik bearbeiten darf, kann das immer.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {leaders.length === 0 ? (
        <p>{t('Noch keine Leitung eingetragen.')}</p>
      ) : (
        <ul className="item-list">
          {leaders.map((l) => (
            <li key={l.id} className="item-row">
              <span className="item-row-info">{l.name}</span>
              {canEdit && (
                <span className="button-row">
                  <button
                    className="button button-ghost"
                    onClick={() => run(() => api.del(`${base}leaders/${l.id}/`))}
                  >
                    {t('Entfernen')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && free.length > 0 && (
        <form
          className="music-toolbar"
          onSubmit={async (e) => {
            e.preventDefault()
            if (!choice) return
            await run(() => api.post(base + 'leaders/', { musician: Number(choice), [key]: id }))
            setChoice('')
          }}
        >
          <label>
            {t('Musiker')}
            <select required value={choice} onChange={(e) => setChoice(e.target.value)}>
              <option value="">—</option>
              {free.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-primary">{t('Als Leitung eintragen')}</button>
        </form>
      )}
    </div>
  )
}
