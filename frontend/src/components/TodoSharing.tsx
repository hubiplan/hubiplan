import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client.ts'
import { todoApi } from '../api/todos.ts'
import type { Todo, TodoShare } from '../api/todos.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'
import { followingChoice } from './TodoSeries.tsx'
import { flushAllForms, useDraftGuard } from './leaveGuard.ts'

interface ChoiceUnit {
  key: string
  organization: number
  department: number | null
  name: string
  users: { id: number; name: string }[]
  roles: { id: number; name: string; has_task_access?: boolean }[]
}

function foreign(entry: TodoShare, todo: Todo) {
  return (
    (entry.target_org ?? todo.organization) !== todo.organization ||
    (entry.target_department ?? null) !== (todo.department ?? null)
  )
}

export function TodoSharing({
  base,
  todo,
  onSaved,
  onDraftChange,
}: {
  base: string
  todo: Todo
  onSaved: () => void
  onDraftChange?: (shares: TodoShare[], perUnit: boolean) => void
}) {
  const { data, error, reload } = useLoad(
    () =>
      api.get<{
        units?: ChoiceUnit[]
        users: { id: number; name: string }[]
        roles: { id: number; name: string; has_task_access?: boolean }[]
      }>(`${base}choices/`),
    [base],
  )
  const [shares, setShares] = useState<TodoShare[]>(todo.shares ?? [])
  const baseline = useRef(JSON.stringify(todo.shares ?? []))
  const version = useRef(todo.version)
  useEffect(() => {
    if (todo.version < version.current) return
    const incoming = JSON.stringify(todo.shares ?? [])
    if (incoming === baseline.current) version.current = todo.version
    else if (JSON.stringify(shares) === baseline.current) {
      baseline.current = incoming
      version.current = todo.version
      setShares(todo.shares ?? [])
    }
  }, [todo, shares])
  const [recipient, setRecipient] = useState('')
  const [unitKey, setUnitKey] = useState('')
  const hasForeign = (todo.shares ?? []).some((entry) => foreign(entry, todo))
  const [perUnit, setPerUnit] = useState(hasForeign ? !!todo.per_unit : true)
  const allUnits = data?.units ?? []
  const units = todo.distributed ? allUnits.slice(0, 1) : allUnits
  const chosen = units.find((unit) => unit.key === unitKey) ?? units[0]
  const choices = chosen ?? data
  const foreignChosen =
    !!chosen &&
    (chosen.organization !== todo.organization ||
      (chosen.department ?? null) !== (todo.department ?? null))
  const foreignShares = shares.some((entry) => foreign(entry, todo))
  const roleName = recipient.startsWith('r:')
    ? choices?.roles.find((role) => role.id === Number(recipient.slice(2)))?.name
    : undefined
  const matchingRoles = roleName
    ? units.flatMap((unit) =>
        unit.roles
          .filter(
            (role) =>
              role.name === roleName &&
              (unit.organization !== todo.organization ||
                (unit.department ?? null) !== (todo.department ?? null)),
          )
          .map((role) => ({ unit, role })),
      )
    : []
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useDraftGuard(JSON.stringify(shares) !== baseline.current, () =>
    setShares(JSON.parse(baseline.current)),
  )
  function append(rows: TodoShare[]) {
    const same = (a: TodoShare, b: TodoShare) =>
      (a.user ?? null) === (b.user ?? null) &&
      (a.role ?? null) === (b.role ?? null) &&
      (a.target_org ?? todo.organization) === (b.target_org ?? todo.organization) &&
      (a.target_department ?? null) === (b.target_department ?? null)
    setShares([...shares, ...rows.filter((row) => !shares.some((old) => same(row, old)))])
    setRecipient('')
  }
  function update(index: number, patch: Partial<TodoShare>) {
    setShares(shares.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }
  useEffect(() => {
    onDraftChange?.(shares, perUnit)
  }, [shares, perUnit, onDraftChange])
  async function save() {
    if (!(await flushAllForms())) return
    const following = todo.series
      ? perUnit && (foreignShares || hasForeign)
        ? true
        : await followingChoice()
      : false
    if (following === null) return
    setBusy(true)
    try {
      const updated = await todoApi.update(base, todo.id, {
        version: version.current,
        shares,
        following,
        ...(foreignShares || hasForeign ? { per_unit: perUnit } : {}),
      })
      baseline.current = JSON.stringify(updated.shares ?? [])
      version.current = updated.version
      onSaved()
      setMessage(t('Gespeichert.'))
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card">
      <h2>{t('Teilen mit')}</h2>
      {error && <LoadError message={error} onRetry={reload} />}
      {data && (
        <>
          {!!units.length && (
            <SelectField
              label={t('Zieleinheit')}
              value={chosen?.key ?? ''}
              onChange={(event) => {
                setUnitKey(event.target.value)
                setRecipient('')
              }}
            >
              {units.map((unit) => (
                <option key={unit.key} value={unit.key}>
                  {unit.name}
                </option>
              ))}
            </SelectField>
          )}
          {(foreignChosen || foreignShares) && (
            <SelectField
              label={t('Erledigung über Einheiten hinweg')}
              disabled={hasForeign}
              value={perUnit ? 'unit' : 'common'}
              onChange={(event) => setPerUnit(event.target.value === 'unit')}
            >
              <option value="unit">{t('je Einheit eine eigene Ausgabe')}</option>
              <option value="common">{t('eine gemeinsame Aufgabe')}</option>
            </SelectField>
          )}
          {todo.series && perUnit && (foreignChosen || foreignShares) && (
            <p className="muted">
              {t(
                'Bei Serien erhält jede Zieleinheit eine eigene Folge mit der zentralen Vorlage. Die Einheit verwaltet ihre lokalen Beteiligten selbst.',
              )}
            </p>
          )}
          <SelectField
            label={t('Empfänger')}
            value={recipient}
            onChange={(event) => setRecipient(event.target.value)}
          >
            <option value="">{t('Bitte wählen')}</option>
            <optgroup label={t('Personen')}>
              {choices?.users.map((u) => (
                <option key={u.id} value={`u:${u.id}`}>
                  {u.name}
                </option>
              ))}
            </optgroup>
            <optgroup label={t('Rollen')}>
              {choices?.roles.map((r) => (
                <option key={r.id} value={`r:${r.id}`}>
                  {r.name}
                  {r.has_task_access === false
                    ? t(' – zusätzliche Aufgabenrechte erforderlich')
                    : ''}
                </option>
              ))}
            </optgroup>
          </SelectField>
          <button
            className="button button-ghost"
            disabled={!recipient}
            onClick={() => {
              const [kind, id] = recipient.split(':')
              append([
                {
                  ...(kind === 'u' ? { user: Number(id) } : { role: Number(id) }),
                  ...(chosen
                    ? { target_org: chosen.organization, target_department: chosen.department }
                    : {}),
                  level: foreignChosen && perUnit ? 'edit' : 'view',
                  responsible: false,
                },
              ])
            }}
          >
            {t('Hinzufügen')}
          </button>
          {!!matchingRoles.length && (
            <button
              className="button button-ghost"
              onClick={() =>
                append(
                  matchingRoles.map(({ unit, role }) => ({
                    role: role.id,
                    target_org: unit.organization,
                    target_department: unit.department,
                    level: perUnit ? 'edit' : 'view',
                    responsible: false,
                  })),
                )
              }
            >
              {t('Rolle „{name}“ in {n} Zieleinheiten hinzufügen', {
                name: roleName!,
                n: matchingRoles.length,
              })}
            </button>
          )}
          {shares.map((entry, index) => (
            <div className="subcard" key={`${entry.user ?? 'r'}:${entry.role ?? 'u'}:${index}`}>
              <p>
                {entry.user
                  ? (
                      allUnits.find(
                        (unit) =>
                          unit.organization === (entry.target_org ?? todo.organization) &&
                          (unit.department ?? null) === (entry.target_department ?? null),
                      )?.users ?? data.users
                    ).find((u) => u.id === entry.user)?.name
                  : (
                      allUnits.find(
                        (unit) =>
                          unit.organization === (entry.target_org ?? todo.organization) &&
                          (unit.department ?? null) === (entry.target_department ?? null),
                      )?.roles ?? data.roles
                    ).find((r) => r.id === entry.role)?.name}
                {foreign(entry, todo) && (
                  <>
                    {' '}
                    ·{' '}
                    {
                      allUnits.find(
                        (unit) =>
                          unit.organization === entry.target_org &&
                          (unit.department ?? null) === (entry.target_department ?? null),
                      )?.name
                    }
                  </>
                )}
              </p>
              <SelectField
                label={t('Berechtigung')}
                value={entry.level}
                onChange={(event) =>
                  update(index, { level: event.target.value as 'view' | 'edit' })
                }
              >
                <option value="view">{t('Lesen')}</option>
                <option value="edit">{t('Bearbeiten')}</option>
              </SelectField>
              <Checkbox
                label={t('Zuständig')}
                checked={entry.responsible}
                onChange={(value) => update(index, { responsible: value })}
              />
              <button
                className="button button-ghost"
                onClick={() => setShares(shares.filter((_, i) => i !== index))}
              >
                {t('Entfernen')}
              </button>
            </div>
          ))}
          {!onDraftChange && (
            <button type="button" className="button" disabled={busy} onClick={() => void save()}>
              {t('Freigaben speichern')}
            </button>
          )}
        </>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
