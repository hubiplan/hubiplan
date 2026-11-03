// Rollen: für jede Einheit dieselbe Liste und dieselbe Maske.
// Was eine Einheit an Angaben zu einer Rolle speichern kann, steht in `fields`;
// die Rechte kommen aus dem Rechtekatalog der Einheit.
import { useId } from 'react'
import type { FormEvent, ReactNode } from 'react'
import type { CatalogModule } from '../api/orgs.ts'
import { levelOf, permissionAreas, withLevel } from './roles.ts'
import type { Level, RoleField, RoleLike, RoleValues } from './roles.ts'
import { Why } from '../learning/Aids.tsx'
import { confirmDialog } from './dialog.ts'
import { useForm } from './forms.ts'
import { Alert, Checkbox, Field } from './ui.tsx'
import { SortHint } from './Sortable.tsx'
import { useSortable } from './useSortable.tsx'
import { t } from '../i18n/index.ts'

/** Angaben einer Rolle; nicht jede Einheit kennt alle. */
function holderText(holders: number | string[]): ReactNode {
  if (typeof holders === 'number') return holders
  return holders.length > 0 ? holders.join(', ') : <span className="muted">unbesetzt</span>
}

function catalogArea(catalog: CatalogModule[], label: string): boolean {
  return catalog.some((m) => m.kind === 'area' && m.label === label)
}

const LEVELS: { level: Level; label: () => string }[] = [
  { level: 'none', label: () => t('kein Zugriff') },
  { level: 'view', label: () => t('lesen') },
  { level: 'edit', label: () => t('bearbeiten') },
]

/** Rechte je Bereich: kein Zugriff, lesen, bearbeiten (Ralf 02.11.); darunter Zusatzrechte */
export function PermissionMatrix({
  catalog,
  codes,
  onChange,
  readOnly = false,
}: {
  catalog: CatalogModule[]
  codes: string[]
  onChange: (codes: string[]) => void
  /** nur ansehen (Leserecht für Rollen) */
  readOnly?: boolean
}) {
  // Mehrere Tabellen auf einer Seite (Zug-Rollen): eigene Namen für die Optionsgruppen
  const group = useId()
  const areas = catalog.filter((m) => m.kind === 'area')
  const extras = catalog.filter((m) => m.kind === 'extras').flatMap((m) => m.permissions)
  const setAll = (level: Level) =>
    onChange(
      areas.reduce(
        (acc, a) => {
          if (level === 'none' || (a.levels ?? []).some((l) => l.level === level)) {
            return withLevel(acc, a, level, catalog)
          }
          // „überall bearbeiten“: Bereiche ohne Bearbeiten bekommen die höchste Stufe;
          // „überall lesen“ lässt Bereiche ohne Lesen (Plattform) unverändert
          const top = a.levels?.[a.levels.length - 1]?.level ?? 'none'
          return level === 'edit' ? withLevel(acc, a, top, catalog) : acc
        },
        level === 'none' ? [] : codes,
      ),
    )
  return (
    <div className="permission-matrix">
      {!readOnly && (
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={() => setAll('view')}>
            {t('überall lesen')}
          </button>
          <button type="button" className="button button-ghost" onClick={() => setAll('edit')}>
            {t('überall bearbeiten')}
          </button>
          <button type="button" className="button button-ghost" onClick={() => setAll('none')}>
            {t('alles entfernen')}
          </button>
        </div>
      )}
      <table className="table permission-table">
        <thead>
          <tr>
            <th>{t('Bereich')}</th>
            {LEVELS.map((l) => (
              <th key={l.level} className="level-cell">
                {l.label()}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {areas.map((a) => {
            const current = levelOf(codes, a)
            const hint = a.levels?.find((l) => l.level === current)?.label
            return (
              <tr key={a.id}>
                <th scope="row">
                  {a.label}
                  {hint && <div className="muted small">{hint}</div>}
                </th>
                {LEVELS.map((l) => {
                  const offered =
                    l.level === 'none' || (a.levels ?? []).some((x) => x.level === l.level)
                  return (
                    <td key={l.level} className="level-cell">
                      {offered ? (
                        <input
                          type="radio"
                          name={`${group}-stufe-${a.id}`}
                          disabled={readOnly}
                          aria-label={`${a.label}: ${l.label()}`}
                          checked={current === l.level}
                          onChange={() => onChange(withLevel(codes, a, l.level, catalog))}
                        />
                      ) : (
                        <span className="muted" aria-hidden="true">
                          –
                        </span>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
      {extras.length > 0 && (
        <fieldset className="permission-group">
          <legend>{t('Zusatzrechte')}</legend>
          {extras.map((p) => {
            const blocked = !!p.needs && !codes.includes(p.needs)
            return (
              <Checkbox
                key={p.code}
                label={p.label}
                checked={codes.includes(p.code)}
                disabled={blocked || readOnly}
                hint={blocked ? t('braucht dafür mindestens „lesen“') : undefined}
                onChange={(on) =>
                  onChange(on ? [...codes, p.code] : codes.filter((c) => c !== p.code))
                }
              />
            )
          })}
        </fieldset>
      )}
    </div>
  )
}

/** Rechte als kurze Bereichsliste statt langem Fließtext (Ralf 31.10.);
 *  die einzelnen Rechte stehen aufklappbar darunter. */
export function PermissionSummary({
  codes,
  catalog,
}: {
  codes: string[]
  catalog: CatalogModule[]
}) {
  const areas = permissionAreas(codes, catalog).map((a, i) => ({
    ...a,
    // Bereiche mit Stufen: Stufe direkt im Kennzeichen („Kasse: lesen“)
    stufe: catalogArea(catalog, a.label) ? a.permissions[0] : undefined,
    key: i,
  }))
  return (
    <>
      <ul className="chips role-areas" aria-label={t('Bereiche')}>
        {areas.map((a) => (
          <li
            key={a.label}
            className={a.full ? 'chip' : 'chip partial'}
            title={a.permissions.join(', ')}
          >
            {a.label}
            {a.stufe ? (
              <span className={a.full ? undefined : 'muted'}>: {a.stufe}</span>
            ) : (
              !a.full && <span className="muted"> (teilweise)</span>
            )}
          </li>
        ))}
      </ul>
      <details className="role-details">
        <summary>{t('Einzelne Rechte')}</summary>
        <ul>
          {areas.map((a) => (
            <li key={a.label}>
              <strong>{a.label}:</strong> {a.permissions.join(', ')}
            </li>
          ))}
        </ul>
      </details>
    </>
  )
}

export function RoleTable({
  roles,
  catalog,
  holderLabel = t('vergeben'),
  onEdit,
  editLabel = t('Bearbeiten'),
  noPermissions = t('keine'),
  showPermissions = true,
  onReorder,
  website = false,
}: {
  roles: RoleLike[]
  catalog: CatalogModule[]
  /** Reihenfolge per Ziehen speichern (fehlt: keine Griffe) */
  onReorder?: (ids: number[]) => Promise<unknown>
  /** Reihenfolge gilt auch für die Webseite (Hinweis) */
  website?: boolean
  holderLabel?: string
  onEdit?: (role: RoleLike) => void
  editLabel?: string
  /** Text für Rollen ohne Rechte */
  noPermissions?: string
  /** aus: Spalte „Berechtigungen“ weglassen (Rollen sind reine Ämter) */
  showPermissions?: boolean
}) {
  const sort = useSortable({
    items: roles,
    id: (r) => r.id,
    label: (r) => r.name,
    onReorder: onReorder ?? (async () => undefined),
    enabled: !!onReorder,
  })
  if (roles.length === 0) return <p className="muted small">{t('Noch keine Rollen.')}</p>
  return (
    <>
      {sort.active && <SortHint website={website} />}
      <table className="table">
        <thead>
          <tr>
            {sort.active && (
              <th className="drag-cell">
                <span className="sr-only">{t('Reihenfolge')}</span>
              </th>
            )}
            <th>{t('Rolle')}</th>
            {showPermissions && <th>{t('Berechtigungen')}</th>}
            <th className={roles.some((r) => typeof r.holders !== 'number') ? '' : 'num'}>
              {holderLabel}
            </th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sort.ordered.map((role) => (
            <tr key={role.id} {...sort.rowProps(role)}>
              {sort.active && <td className="drag-cell">{sort.handle(role)}</td>}
              <td>
                <strong>{role.name}</strong>
                {role.description && <div className="muted small">{role.description}</div>}
              </td>
              {showPermissions && (
                <td className="small">
                  {role.permissions.length === 0 ? (
                    noPermissions
                  ) : (
                    <PermissionSummary codes={role.permissions} catalog={catalog} />
                  )}
                </td>
              )}
              <td className={typeof role.holders === 'number' ? 'num' : 'small'}>
                {holderText(role.holders)}
              </td>
              <td className="actions">
                {onEdit && (
                  <button type="button" className="link-button" onClick={() => onEdit(role)}>
                    {editLabel}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {sort.status}
    </>
  )
}

export function RoleForm({
  role,
  catalog,
  fields,
  hasWebsite,
  onSave,
  onDelete,
  confirmDelete,
  onDone,
  onCancel,
  readOnly = false,
  permissionsOptional = false,
  showPermissions = true,
}: {
  role: RoleLike | null
  catalog: CatalogModule[]
  fields: RoleField[]
  hasWebsite: boolean
  onSave: (values: Partial<RoleValues>) => Promise<unknown>
  onDelete?: () => Promise<unknown>
  /** Rückfrage vor dem Löschen; ohne Angabe eine einfache Rückfrage */
  confirmDelete?: () => Promise<boolean>
  onDone: () => void
  onCancel: () => void
  readOnly?: boolean
  /** Rechte nur für Zugänge: zugeklappt, Rolle ohne Rechte ist ein reines Amt */
  permissionsOptional?: boolean
  /** aus: keine Rechte zeigen (Rollen sind reine Ämter) */
  showPermissions?: boolean
}) {
  const form = useForm<RoleValues>({
    name: role?.name ?? '',
    description: role?.description ?? '',
    is_board: role?.is_board ?? true,
    represents: role?.represents ?? false,
    on_letterhead: role?.on_letterhead ?? false,
    contact_email: role?.contact_email ?? '',
    on_website: role?.on_website ?? false,
    in_chronicle: role?.in_chronicle ?? false,
    permissions: role?.permissions ?? [],
  })
  const { values: v } = form
  const has = (f: RoleField) => fields.includes(f)
  const web = hasWebsite && has('on_website')

  function toggle(code: string, on: boolean) {
    form.set('permissions', on ? [...v.permissions, code] : v.permissions.filter((c) => c !== code))
  }

  const staged = catalog.some((m) => m.kind === 'area')
  const permissionGrid = staged ? (
    <PermissionMatrix
      catalog={catalog}
      codes={v.permissions}
      onChange={(codes) => form.set('permissions', codes)}
    />
  ) : (
    <div className="permission-grid">
      {catalog.map((module) => (
        <fieldset key={module.id} className="permission-group">
          <legend>{module.label}</legend>
          {module.permissions.map((p) => (
            <Checkbox
              key={p.code}
              label={p.label}
              checked={v.permissions.includes(p.code)}
              onChange={(on) => toggle(p.code, on)}
            />
          ))}
        </fieldset>
      ))}
    </div>
  )

  async function save(e: FormEvent) {
    e.preventDefault()
    const data: Partial<RoleValues> = { name: v.name, permissions: v.permissions }
    for (const f of fields) (data as Record<string, unknown>)[f] = v[f]
    const ok = await form.submit(() => onSave(data))
    if (ok) onDone()
  }

  async function remove() {
    if (!role || !onDelete) return
    const ok = confirmDelete
      ? await confirmDelete()
      : await confirmDialog({
          title: t('Rolle „{name}“ löschen?', { name: role.name }),
          confirmLabel: t('Löschen'),
        })
    if (!ok) return
    const done = await form.submit(onDelete)
    if (done !== undefined) onDone()
  }

  return (
    <form className="subcard" onSubmit={save}>
      <h3>{role ? t('Rolle „{name}“ bearbeiten', { name: role.name }) : t('Neue Rolle')}</h3>
      <fieldset disabled={readOnly}>
        <div className="grid-2">
          <Field
            label={t('Name')}
            required
            value={v.name}
            error={form.errors.name}
            placeholder={t('z. B. Kassierer oder Schriftführer')}
            onChange={(e) => form.set('name', e.target.value)}
          />
          {has('description') && (
            <Field
              label={t('Beschreibung')}
              value={v.description}
              error={form.errors.description}
              onChange={(e) => form.set('description', e.target.value)}
            />
          )}
        </div>
        {has('is_board') && (
          <Checkbox
            label={t('Vorstandsrolle (kann Kontakt der Organisation sein)')}
            checked={v.is_board}
            onChange={(val) => form.set('is_board', val)}
          />
        )}
        {has('represents') && (
          <Checkbox
            label={t('vertritt die Einheit (§ 26 BGB): Inhaber stehen im Impressum')}
            checked={v.represents}
            onChange={(val) => form.set('represents', val)}
          />
        )}
        {has('on_letterhead') && (
          <Checkbox
            label={t('auf dem Briefbogen nennen: Inhaber stehen in der Fußzeile der Briefvorlage')}
            checked={v.on_letterhead}
            onChange={(val) => form.set('on_letterhead', val)}
          />
        )}
        {has('contact_email') && (
          <Field
            label={t('Funktionsadresse (E-Mail, optional)')}
            type="email"
            value={v.contact_email}
            error={form.errors.contact_email}
            hint={t('z. B. kassierer@… – Inhaber können sie in der Briefvorlage angeben.')}
            onChange={(e) => form.set('contact_email', e.target.value)}
          />
        )}
        {web && (
          <Checkbox
            label={t(
              'auf der Webseite zeigen: Inhaber erscheinen unter Vorstand und Ansprechpartner',
            )}
            checked={v.on_website}
            onChange={(val) => form.set('on_website', val)}
          />
        )}
        {hasWebsite && has('in_chronicle') && (
          <Checkbox
            label={t(
              'unter „Ämter“ zeigen: heutige und frühere Inhaber erscheinen auf der Webseite unter Geschichte › Ämter (z. B. Vorsitzende seit …)',
            )}
            checked={v.in_chronicle}
            onChange={(val) => form.set('in_chronicle', val)}
          />
        )}
        <div className="aid-row">
          {has('represents') && <Why k="role_represents" />}
          {showPermissions && <Why k="role_permissions" />}
        </div>
        {!showPermissions ? null : permissionsOptional ? (
          <details className="permission-details" open={(role?.permissions.length ?? 0) > 0}>
            <summary>
              {t('Rechte für Zugänge (optional)')}
              {v.permissions.length > 0 && t(' · {n} gewählt', { n: v.permissions.length })}
            </summary>
            <p className="muted small">
              {t(
                'Ohne Rechte ist die Rolle nur ein Amt: Die Inhaber brauchen kein Konto und bekommen keine E-Mail. Rechte braucht es nur, wenn ein Inhaber selbst in HUBIplan arbeiten soll.',
              )}
            </p>
            {permissionGrid}
          </details>
        ) : (
          permissionGrid
        )}
      </fieldset>
      {form.errors.permissions && <Alert kind="error">{form.errors.permissions}</Alert>}
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        {!readOnly && (
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Speichern')}
          </button>
        )}
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {readOnly ? t('Schließen') : t('Abbrechen')}
        </button>
        {role && onDelete && !readOnly && (
          <button type="button" className="button button-danger push-right" onClick={remove}>
            {t('Löschen')}
          </button>
        )}
      </div>
    </form>
  )
}
