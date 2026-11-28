import { useState } from 'react'
import { todayIso } from '../../api/members.ts'
import { t } from '../../i18n/index.ts'

export function AddWithDate({
  label,
  options,
  onAdd,
  withEnd = false,
}: {
  label: string
  options: { id: number; name: string; needsEnd?: boolean }[]
  onAdd: (id: number, date: string, until: string | null) => Promise<void>
  // Optionales Ende, damit sich frühere Zeiten in einem Schritt nachtragen lassen
  withEnd?: boolean
}) {
  const [id, setId] = useState('')
  const [date, setDate] = useState(todayIso)
  const [until, setUntil] = useState('')
  const needsEnd = options.some((o) => String(o.id) === id && o.needsEnd)
  return (
    <form
      className="inline-add"
      onSubmit={(e) => {
        e.preventDefault()
        if (id)
          void onAdd(Number(id), date, until || null).then(() => {
            setId('')
            setUntil('')
          })
      }}
    >
      <select aria-label={label} value={id} onChange={(e) => setId(e.target.value)}>
        <option value="">{label} …</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      <input
        type="date"
        aria-label={t('ab')}
        value={date}
        onChange={(e) => setDate(e.target.value)}
      />
      {withEnd && (
        <input
          type="date"
          aria-label={t('bis (leer = heute)')}
          title={t('bis (leer = heute)')}
          value={until}
          min={date}
          required={needsEnd}
          onChange={(e) => setUntil(e.target.value)}
        />
      )}
      <button type="submit" className="button button-ghost">
        {t('Hinzufügen')}
      </button>
    </form>
  )
}
