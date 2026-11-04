import { useState } from 'react'
import { api, newRequestKey } from '../../api/client.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

type Template = { id: number; name: string; fee: string; allowance: string; active: boolean }

export function FeeBatchPanel({
  url,
  assignments,
  onSaved,
}: {
  url: string
  assignments: { id: number; name: string }[]
  onSaved: () => Promise<unknown>
}) {
  const org = useActiveOrg()
  const base = `/api/orgs/${org.id}/music/fee-templates/`
  const load = useLoad(() => api.get<Template[]>(base), [org.id])
  const [template, setTemplate] = useState('')
  const [rows, setRows] = useState<Record<number, boolean>>({})
  const [name, setName] = useState('')
  const [fee, setFee] = useState('0')
  const [allowance, setAllowance] = useState('0')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [key, setKey] = useState(newRequestKey)
  useDraftGuard(Object.keys(rows).length > 0 || name !== '')
  const change = (next: Record<number, boolean>) => {
    setRows(next)
    setKey(newRequestKey())
  }
  async function save() {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await api.post(
        url,
        {
          action: 'batch_claims',
          template: Number(template),
          rows: Object.entries(rows).map(([assignment, attended]) => ({
            assignment: Number(assignment),
            attended,
          })),
        },
        key,
      )
      setRows({})
      setKey(newRequestKey())
      await onSaved()
      setMessage(t('Vergütungsentwürfe wurden angelegt.'))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack music-record">
      <h3>{t('Vergütungsvorlagen und Sammelabrechnung')}</h3>
      <p>
        {t(
          'Vorlagen übernehmen Gage und Pauschale. Auslagen und Freigaben werden je Musiker geprüft.',
        )}
      </p>
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      {message && <Alert kind="success">{message}</Alert>}
      <label>
        {t('Vergütungsvorlage')}
        <select
          value={template}
          disabled={busy}
          onChange={(e) => {
            setTemplate(e.target.value)
            setKey(newRequestKey())
          }}
        >
          <option value="">{t('Bitte wählen')}</option>
          {load.data
            ?.filter((x) => x.active)
            .map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} · {euro(x.fee)} + {euro(x.allowance)}
              </option>
            ))}
        </select>
      </label>
      <button
        className="button button-ghost"
        disabled={busy || !assignments.length}
        onClick={() => change(Object.fromEntries(assignments.map((a) => [a.id, false])))}
      >
        {t('Alle ohne Vergütung auswählen')}
      </button>
      {assignments.map((a) => (
        <div className="music-actions" key={a.id}>
          <label>
            <input
              type="checkbox"
              disabled={busy}
              checked={a.id in rows}
              onChange={(e) => {
                const next = { ...rows }
                if (e.target.checked) next[a.id] = false
                else delete next[a.id]
                change(next)
              }}
            />
            {a.name}
          </label>
          {a.id in rows && (
            <label>
              <input
                type="checkbox"
                disabled={busy}
                checked={rows[a.id]}
                onChange={(e) => change({ ...rows, [a.id]: e.target.checked })}
              />
              {t('Teilnahme bestätigt für {name}', { name: a.name })}
            </label>
          )}
        </div>
      ))}
      <button
        className="button button-primary"
        disabled={busy || !template || !Object.keys(rows).length}
        onClick={() => void save()}
      >
        {t('Vergütungsentwürfe anlegen')}
      </button>
      <details>
        <summary>{t('Vergütungsvorlagen verwalten')}</summary>
        <form
          className="stack"
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            setError('')
            try {
              await api.post(base, { name, fee, allowance, active: true })
              setName('')
              setFee('0')
              setAllowance('0')
              await load.reload()
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          <label>
            {t('Name der Vergütungsvorlage')}
            <input
              required
              maxLength={150}
              disabled={busy}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div className="music-form-fields">
            {[
              [t('Gage'), fee, setFee],
              [t('Pauschale'), allowance, setAllowance],
            ].map(([label, value, setter]) => (
              <label key={String(label)}>
                {String(label)}
                <input
                  required
                  type="number"
                  min="0"
                  max="9999999999.99"
                  step="0.01"
                  disabled={busy}
                  value={String(value)}
                  onChange={(e) => (setter as (v: string) => void)(e.target.value)}
                />
              </label>
            ))}
          </div>
          <button className="button button-ghost" disabled={busy}>
            {t('Vergütungsvorlage speichern')}
          </button>
        </form>
        {load.data
          ?.filter((x) => x.active)
          .map((x) => (
            <div className="music-actions" key={x.id}>
              <span>{x.name}</span>
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  setError('')
                  try {
                    await api.patch(`${base}${x.id}/`, { active: false })
                    if (template === String(x.id)) setTemplate('')
                    await load.reload()
                  } catch (e) {
                    setError(errorMessage(e))
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                {t('Vorlage archivieren: {name}', { name: x.name })}
              </button>
            </div>
          ))}
      </details>
    </section>
  )
}
