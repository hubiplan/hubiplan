import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { orgApi, PERM } from '../../api/orgs.ts'
import type { Department } from '../../api/orgs.ts'
import { Alert, Field, SelectField, Loading } from '../../components/ui.tsx'
import { errorMessage, useForm, useLoad } from '../../components/forms.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { fillTerms, termsFor, useTerms } from '../../org/terms.ts'
import type { DeptTerms } from '../../org/terms.ts'
import { alertDialog, confirmDialog } from '../../components/dialog.ts'
import { DataTable } from '../../components/DataTable.tsx'
import type { Column } from '../../components/DataTable.tsx'
import { DeleteIcon, EditIcon, IconButton, ViewIcon } from '../../components/icons.tsx'
import { HowTo } from '../../learning/Aids.tsx'
import { SortableList, SortHint } from '../../components/Sortable.tsx'
import { lang, t } from '../../i18n/index.ts'
import { useDepartmentChoices } from '../../components/masterData.ts'
import { DepartmentCard } from './DepartmentCard.tsx'
import { DepartmentRolesPanel } from './DepartmentRolesPanel.tsx'

export function DepartmentsPage() {
  const { can } = useOrg()
  return can(PERM.settingsView) ? <DepartmentSettingsPage /> : <DepartmentRolesPage />
}

function DepartmentRolesPage() {
  const org = useActiveOrg()
  const { can } = useOrg()
  const terms = useTerms()
  const { data, error, reload } = useDepartmentChoices(org.id)
  const catalog = useLoad(
    () => orgApi.catalog('department', org.id),
    [org.id, org.modules.join(',')],
  )
  const [selected, setSelected] = useState('')
  if (!can(PERM.rolesView)) return null
  if (error || catalog.error) return <Alert kind="error">{error || catalog.error}</Alert>
  if (!data || !catalog.data) return <Loading />
  const dep = data.find((d) => String(d.id) === selected) ?? data[0]
  return (
    <div className="card card-wide">
      <SelectField
        label={terms.Sg}
        value={dep ? String(dep.id) : ''}
        onChange={(e) => setSelected(e.target.value)}
      >
        {data.map((d) => (
          <option key={d.id} value={d.id}>
            {d.path || d.name}
          </option>
        ))}
      </SelectField>
      {dep && (
        <DepartmentRolesPanel
          key={dep.id}
          orgId={org.id}
          dep={dep}
          inThis={dep.name}
          editable={can(PERM.rolesManage)}
          catalog={catalog.data}
          onChange={reload}
        />
      )}
    </div>
  )
}

function DepartmentSettingsPage() {
  const org = useActiveOrg()
  const editable = org.permissions.includes(PERM.orgEdit)
  const { data, error, reload } = useLoad(() => orgApi.departments(org.id), [org.id])
  const catalog = useLoad(
    () => orgApi.catalog('department', org.id),
    [org.id, org.modules.join(',')],
  )
  const tmx = useTerms()
  const label = tmx.sg
  const labelPlural = tmx.pl
  const [selected, setSelected] = useState<number | null>(null)
  const [sorting, setSorting] = useState(false)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (selected !== null) panel.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [selected])

  if (org.type !== 'club')
    return (
      <Alert kind="info">
        {t('Nur Einheiten mit Mitgliedern haben {labelPlural}.', { labelPlural })}
      </Alert>
    )
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  const current = data.find((d) => d.id === selected) ?? null

  async function remove(dep: Department) {
    const own = ownTerms(dep, tmx)
    const ok = await confirmDialog({
      final: false,
      title: t('„{name}“ löschen?', { name: dep.name }),
      message: fillTerms(
        t('Nur möglich, solange {diesem} keine Mitglieder und Rolleninhaber zugeordnet sind ') +
          t('oder waren und {nom} keine eigenen Untereinheiten hat. Sonst {akk} besser auf ') +
          t('inaktiv setzen.'),
        own,
      ),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await orgApi.deleteDepartment(org.id, dep.id)
      if (selected === dep.id) setSelected(null)
      reload()
    } catch (err) {
      await alertDialog({
        title: t('{Sg} nicht gelöscht', { Sg: own.Sg }),
        message: errorMessage(err),
      })
    }
  }

  const columns: Column<Department>[] = [
    {
      key: 'name',
      label: t('Name'),
      value: (d) => d.path ?? d.name,
      searchText: (d) => t('{x} {x2}', { x: d.path ?? d.name, x2: d.short_name ?? '' }),
      render: (d) => (
        <span
          className="cell-with-logo"
          style={d.depth ? { paddingLeft: `${d.depth * 1.5}rem` } : undefined}
          data-depth={d.depth ?? 0}
        >
          {(d.depth ?? 0) > 0 && (
            <span className="muted" aria-hidden="true">
              ↳
            </span>
          )}
          {d.logo_url && <img src={d.logo_url} alt="" className="cell-logo" />}
          {d.name}
          {(d.depth ?? 0) > 0 && d.label && (
            <span className="muted small">{(lang() === 'en' && d.label_en) || d.label}</span>
          )}
        </span>
      ),
    },
    { key: 'short_name', label: t('Kurzname'), value: (d) => d.short_name ?? '', optional: true },
    {
      key: 'founding_year',
      label: t('Gründungsjahr'),
      value: (d) => d.founding_year,
      numeric: true,
      optional: true,
    },
    { key: 'members', label: t('Mitglieder'), value: (d) => d.member_count ?? 0, numeric: true },
    {
      key: 'roles',
      label: t('Rollen'),
      value: (d) => d.roles.length,
      searchText: (d) => d.roles.map((r) => r.name).join(' '),
      render: (d) =>
        d.roles.length === 0 ? (
          <span className="muted">–</span>
        ) : (
          <span title={d.roles.map((r) => r.name).join(', ')}>{d.roles.length}</span>
        ),
      numeric: true,
      optional: true,
    },
    {
      key: 'status',
      label: t('Status'),
      value: (d) => (d.is_remote ? t('andere Instanz') : d.is_active ? t('aktiv') : t('inaktiv')),
      filter: {
        allLabel: t('aktive und inaktive'),
        options: [
          { value: t('aktiv'), label: t('nur aktive') },
          { value: t('inaktiv'), label: t('nur inaktive') },
        ],
      },
    },
  ]

  return (
    <div className="stack">
      <div className="card card-wide">
        <div className="card-head">
          <HowTo k="how_units" />
          {editable && data.length > 1 && (
            <button
              type="button"
              className="button button-ghost push-right"
              aria-pressed={sorting}
              onClick={() => setSorting((x) => !x)}
            >
              {sorting ? t('Schließen') : t('Reihenfolge ändern')}
            </button>
          )}
        </div>
        {sorting ? (
          <>
            <SortHint website={org.modules.includes('website')} />
            <UnitOrder orgId={org.id} units={data} parent={null} onChange={reload} />
          </>
        ) : (
          <DataTable
            label={labelPlural}
            rows={data}
            columns={columns}
            rowKey={(d) => d.id}
            searchPlaceholder={t('{labelPlural} durchsuchen: Name, Kurzname, Rolle', {
              labelPlural,
            })}
            emptyText={t('Noch keine {labelPlural} angelegt.', { labelPlural })}
            countText={(n, total) =>
              n === total
                ? levelCounts(data, label, labelPlural)
                : t('{n} von {total}', { n, total })
            }
            rowClassName={(d) =>
              [!d.is_active && 'inactive', d.id === selected && 'selected']
                .filter(Boolean)
                .join(' ') || undefined
            }
            actions={(d) => (
              <>
                <IconButton
                  label={t('{name} {x}', {
                    name: d.name,
                    x: editable && !d.is_remote ? t('bearbeiten') : t('anzeigen'),
                  })}
                  icon={editable && !d.is_remote ? <EditIcon /> : <ViewIcon />}
                  aria-pressed={d.id === selected}
                  onClick={() => setSelected((s) => (s === d.id ? null : d.id))}
                />
                {editable && !d.is_remote && (
                  <IconButton
                    label={t('{name} löschen', { name: d.name })}
                    icon={<DeleteIcon />}
                    danger
                    onClick={() => void remove(d)}
                  />
                )}
              </>
            )}
          />
        )}
      </div>
      {current && (
        <div ref={panel}>
          <DepartmentCard
            key={current.id}
            orgId={org.id}
            dep={current}
            units={data}
            terms={tmx}
            inThis={ownTerms(current, tmx).diesem}
            editable={editable && !current.is_remote}
            catalog={catalog.data ?? []}
            onChange={reload}
            onClose={() => setSelected(null)}
          />
        </div>
      )}
      {editable && (
        <NewDepartment
          key={current?.id ?? 0}
          orgId={org.id}
          units={data}
          terms={tmx}
          initialParent={current?.id ?? null}
          onCreated={reload}
        />
      )}
    </div>
  )
}

/** Formen für die Bezeichnung einer Untereinheit selbst (z. B. „Gruppe“). */
function ownTerms(dep: Department, fallback: DeptTerms): DeptTerms {
  if (!dep.label || dep.depth === 0) return fallback
  return termsFor(
    dep.label,
    dep.label_plural ?? dep.label,
    dep.label_gender ?? 'f',
    '',
    dep.label_en,
    dep.label_plural_en,
  )
}

/** Formen für Untereinheiten unter ``parent`` (oder direkt unter der Einheit). */
function childTermsOf(parent: Department | undefined, fallback: DeptTerms): DeptTerms {
  return parent?.child_terms && Object.keys(parent.child_terms).length
    ? parent.child_terms
    : fallback
}

function NewDepartment({
  orgId,
  units,
  terms,
  initialParent,
  onCreated,
}: {
  orgId: number
  units: Department[]
  terms: DeptTerms
  initialParent: number | null
  onCreated: () => void
}) {
  const form = useForm({
    name: '',
    short_name: '',
    founding_year: '',
    parent_unit: initialParent ? String(initialParent) : '',
  })
  const parent = units.find((u) => String(u.id) === form.values.parent_unit)
  const label = childTermsOf(parent, terms).sg
  async function create(e: FormEvent) {
    e.preventDefault()
    const ok = await form.submit(
      () =>
        orgApi.createDepartment(orgId, {
          name: form.values.name,
          short_name: form.values.short_name,
          founding_year: form.values.founding_year ? Number(form.values.founding_year) : null,
          parent_unit: form.values.parent_unit ? Number(form.values.parent_unit) : null,
        }),
      t('{label} angelegt.', { label }),
    )
    if (ok) {
      form.setValues({
        name: '',
        short_name: '',
        founding_year: '',
        parent_unit: form.values.parent_unit,
      })
      onCreated()
    }
  }
  return (
    <form className="card" onSubmit={create}>
      <h2>
        {label} {t('anlegen')}
      </h2>
      <SelectField
        label={t('Gehört zu')}
        value={form.values.parent_unit}
        error={form.errors.parent_unit}
        hint={t('Untereinheiten können selbst wieder Untereinheiten haben.')}
        onChange={(e) => form.set('parent_unit', e.target.value)}
      >
        <option value="">
          {t('direkt')} {terms.e_zum}
        </option>
        {units
          .filter((u) => u.is_active)
          .map((u) => (
            <option key={u.id} value={String(u.id)}>
              {u.path ?? u.name}
            </option>
          ))}
      </SelectField>
      <div className="grid-3">
        <Field
          label={t('Vollständiger Name')}
          required
          value={form.values.name}
          error={form.errors.name}
          onChange={(e) => form.set('name', e.target.value)}
        />
        <Field
          label={t('Kurzname (optional)')}
          maxLength={50}
          value={form.values.short_name}
          error={form.errors.short_name}
          hint={t('Für Navigation, Listen und Auswahlfelder')}
          onChange={(e) => form.set('short_name', e.target.value)}
        />
        <Field
          label={t('Gründungsjahr (optional)')}
          type="number"
          min={800}
          max={2100}
          value={form.values.founding_year}
          error={form.errors.founding_year}
          onChange={(e) => form.set('founding_year', e.target.value)}
        />
      </div>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <button type="submit" className="button button-primary" disabled={form.busy}>
        {t('Anlegen')}
      </button>
    </form>
  )
}

/** Reihenfolge der Untereinheiten: je Ebene eine Liste zum Ziehen. */
function UnitOrder({
  orgId,
  units,
  parent,
  onChange,
}: {
  orgId: number
  units: Department[]
  parent: number | null
  onChange: () => unknown
}) {
  const children = units.filter((u) => (u.parent_unit ?? null) === parent)
  if (children.length === 0) return null
  return (
    <SortableList
      ariaLabel={parent === null ? t('Reihenfolge') : t('Reihenfolge darunter')}
      items={children}
      id={(u) => u.id}
      label={(u) => u.name}
      onReorder={(ids) => orgApi.reorderDepartments(orgId, parent, ids).then(() => onChange())}
      render={(u) => (
        <>
          <span className={u.is_active ? undefined : 'muted'}>
            {u.name}
            {!u.is_active && t(' (inaktiv)')}
          </span>
          <UnitOrder orgId={orgId} units={units} parent={u.id} onChange={onChange} />
        </>
      )}
    />
  )
}

/** Anzahl je Ebene („6 Korps · 16 Züge“), damit tiefere Ebenen nicht unter der obersten Bezeichnung mitgezählt werden. */
function levelCounts(rows: Department[], label: string, labelPlural: string): string {
  const en = lang() === 'en'
  const groups = new Map<string, { sg: string; pl: string; n: number }>()
  for (const d of rows) {
    const sg = (en && d.label_en) || d.label || label
    const pl = (en && d.label_plural_en) || d.label_plural || (sg === label ? labelPlural : sg)
    const g = groups.get(sg) ?? { sg, pl, n: 0 }
    g.n += 1
    groups.set(sg, g)
  }
  return [...groups.values()]
    .map((g) => t('{total} {x}', { total: g.n, x: g.n === 1 ? g.sg : g.pl }))
    .join(' · ')
}
