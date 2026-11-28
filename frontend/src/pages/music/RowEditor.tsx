import { useEffect, useState } from 'react'
import { memberApi } from '../../api/members.ts'
import type { PickedMember } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { useAutoSave } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { SaveStatus } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { InstrumentSelect } from './InstrumentSelect.tsx'
import type { Instrument } from './InstrumentSelect.tsx'
import { type Field, type Row } from './musicHelpers.ts'

export function RowEditor({
  fields,
  instruments,
  row,
  defaults,
  onClose,
  onSave,
  onAutoSave,
}: {
  fields: Field[]
  /** Auswahl für Felder vom Typ „instrument“ */
  instruments: Instrument[]
  row?: Row
  defaults: Record<string, string>
  onClose: () => void
  onSave: (values: Record<string, unknown>) => Promise<void>
  /** Vorhandener Eintrag: geänderte Felder automatisch speichern */
  onAutoSave?: (changes: Record<string, unknown>) => Promise<void>
}) {
  const initial = Object.fromEntries(
    fields.map((f) => [
      f.key,
      row?.[f.key] ??
        (defaults[f.key] ||
          (f.type === 'checkbox'
            ? f.key === 'active'
            : f.type === 'number'
              ? (f.initial ?? 1)
              : f.optional
                ? ''
                : f.options?.[0]?.[0] || '')),
    ]),
  )
  for (const field of fields) {
    if (field.type === 'datetime-local' && initial[field.key]) {
      const date = new Date(String(initial[field.key]))
      initial[field.key] = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16)
    }
  }
  const [values, setValues] = useState(initial)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [, setErrors] = useState<Record<string, string>>({})
  const prepare = (v: Record<string, unknown>) =>
    Object.fromEntries(
      Object.entries(v).map(([key, value]) => {
        const f = fields.find((x) => x.key === key)
        return [
          key,
          value === '' && (f?.options || f?.member)
            ? null
            : f?.type === 'datetime-local' && value
              ? new Date(String(value)).toISOString()
              : f?.type === 'datetime-local'
                ? null
                : value,
        ]
      }),
    )
  const auto = useAutoSave(
    { values, setErrors, setValues },
    (changes) => onAutoSave!(prepare(changes)),
    { enabled: !!onAutoSave },
  )
  useDraftGuard(!onAutoSave && dirty)
  return (
    <form
      className="card stack"
      onSubmit={async (e) => {
        e.preventDefault()
        if (onAutoSave) return
        setBusy(true)
        try {
          await onSave(prepare(values))
        } finally {
          setBusy(false)
        }
      }}
    >
      {onAutoSave && <SaveStatus auto={auto} />}
      <div className="music-form-fields">
        {fields.map((f) =>
          f.member ? (
            <MemberField
              key={f.key}
              label={f.label}
              id={String(values[f.key] ?? '')}
              fixedName={row ? String(row.display_name || '') : undefined}
              onChange={(id) => {
                setValues((v) => ({ ...v, [f.key]: id }))
                setDirty(true)
              }}
            />
          ) : (
            <label key={f.key} className={f.type === 'textarea' ? 'music-field-wide' : undefined}>
              {f.label}
              {f.type === 'instrument' ? (
                <InstrumentSelect
                  instruments={instruments}
                  value={String(values[f.key] ?? '')}
                  onChange={(value) => {
                    setValues((v) => ({ ...v, [f.key]: value }))
                    setDirty(true)
                  }}
                />
              ) : f.options ? (
                <select
                  required={!f.optional}
                  value={String(values[f.key] ?? '')}
                  disabled={
                    (!!row &&
                      ['membership', 'event', 'performance', 'position', 'musician'].includes(
                        f.key,
                      )) ||
                    !!f.lockedBy?.(values)
                  }
                  onChange={(e) => {
                    const value = e.target.value
                    setValues((v) => ({
                      ...v,
                      [f.key]: value,
                      ...(f.suggest && value ? f.suggest(value) : {}),
                    }))
                    setDirty(true)
                  }}
                >
                  {f.optional && <option value="">—</option>}
                  {f.options.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              ) : null}
              {f.options && f.lockedBy?.(values) ? (
                <small className="muted">{f.lockedBy(values)}</small>
              ) : f.options || f.type === 'instrument' ? null : f.type === 'textarea' ? (
                <textarea
                  value={String(values[f.key])}
                  onChange={(e) => {
                    setValues((v) => ({ ...v, [f.key]: e.target.value }))
                    setDirty(true)
                  }}
                />
              ) : (
                <input
                  required={!f.optional && f.type !== 'checkbox'}
                  type={f.type || 'text'}
                  min={f.type === 'number' ? (f.min ?? 1) : undefined}
                  max={f.type === 'number' ? (f.max ?? 500) : undefined}
                  value={f.type === 'checkbox' ? undefined : String(values[f.key] ?? '')}
                  checked={f.type === 'checkbox' ? Boolean(values[f.key]) : undefined}
                  onChange={(e) => {
                    const value = f.type === 'checkbox' ? e.target.checked : e.target.value
                    setValues((v) => ({ ...v, [f.key]: value }))
                    setDirty(true)
                  }}
                />
              )}
            </label>
          ),
        )}
      </div>
      <div className="actions">
        {onAutoSave ? (
          <button
            className="button"
            type="button"
            onClick={async () => {
              // Schließt erst, wenn alles gespeichert ist
              if (await auto.flush()) onClose()
            }}
          >
            {t('Schließen')}
          </button>
        ) : (
          <>
            <button className="button button-primary" disabled={busy}>
              {t('Speichern')}
            </button>
            <button className="button button-ghost" type="button" onClick={onClose}>
              {t('Abbrechen')}
            </button>
          </>
        )}
      </div>
    </form>
  )
}

/** Mitglied eines Musikers: beim Anlegen per Suche, danach unveränderlich. */
function MemberField({
  label,
  id,
  fixedName,
  onChange,
}: {
  label: string
  id: string
  fixedName?: string
  onChange: (id: string) => void
}) {
  const org = useActiveOrg()
  const [picked, setPicked] = useState<PickedMember | null>(null)
  // Vorbelegung aus der Mitgliedsakte: den Namen zur Nummer nachladen
  const pending = fixedName === undefined && !!id && String(picked?.id) !== id
  useEffect(() => {
    if (!pending) return
    let alive = true
    memberApi
      .detail(org.id, Number(id))
      .then((m) => {
        if (alive) setPicked({ id: m.id, first_name: m.first_name, last_name: m.last_name })
      })
      .catch(() => alive && onChange(''))
    return () => {
      alive = false
    }
  }, [org.id, id, pending, onChange])
  if (fixedName !== undefined)
    return id ? (
      <div className="field">
        <span>{label}</span>
        <p>{fixedName}</p>
      </div>
    ) : null
  if (pending)
    return (
      <div className="field">
        <span>{label}</span>
        <p className="muted">{t('Wird geladen …')}</p>
      </div>
    )
  return (
    <MemberPicker<PickedMember>
      orgId={org.id}
      value={picked}
      label={label}
      onChange={(m) => {
        setPicked(m)
        onChange(m ? String(m.id) : '')
      }}
    />
  )
}
