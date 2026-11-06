// Abteilungsbereich: was Inhaber von Abteilungsrollen sehen und tun dürfen.
import { useEffect, useState } from 'react'
import { SortHint } from '../../components/Sortable.tsx'
import { useSortable } from '../../components/useSortable.tsx'
import type { FormEvent } from 'react'
import { Link, Route, Routes, useParams } from 'react-router-dom'
import { SubpageUnavailable } from '../NoticePages.tsx'
import type { MemberRow, Page } from '../../api/members.ts'
import { DEPT_PERM, portalApi } from '../../api/portal.ts'
import type { DeptMember, DeptRole, DeptSummary, Holder } from '../../api/portal.ts'
import { AccessPanel } from '../../components/AccessPanel.tsx'
import { CardPanel } from '../../components/CardPanel.tsx'
import { cardApi, cardBase } from '../../api/cards.ts'
import { ExportSection } from '../../components/DataTransfer.tsx'
import {
  errorMessage,
  formatDate,
  formatMemberDate,
  useAutoSave,
  useForm,
  useLoad,
} from '../../components/forms.ts'
import {
  Alert,
  Checkbox,
  Field,
  SaveStatus,
  Tabs,
  LoadError,
  Freshness,
} from '../../components/ui.tsx'
import { Term } from '../../learning/Aids.tsx'
import { useActiveDept } from '../../org/OrgContext.tsx'
import { DeptInvoices } from '../billing/MyInvoices.tsx'
import { DeptEntries } from '../entries/UnitEntries.tsx'
import { MovedCirculars } from '../circulars/CircularsPage.tsx'
import { MemberDevelopment } from '../members/DevelopmentPage.tsx'
import { statsApi } from '../../api/statistics.ts'
import { alertDialog, confirmRoleRemoval } from '../../components/dialog.ts'
import { confirmEndHolder, UnitRoleDialog, UnitRolesTable } from '../../components/UnitRoles.tsx'
import type { UnitRole } from '../../components/UnitRoles.tsx'
import { t } from '../../i18n/index.ts'
import { PermissionMatrix, PermissionSummary } from '../../components/RoleEditor.tsx'

export function DepartmentArea() {
  const dept = useActiveDept()
  const can = (p: string) => dept.permissions.includes(p)
  const tabs = [
    ...(can(DEPT_PERM.membersView) || !can(DEPT_PERM.invoicesView)
      ? [{ to: '/abteilung', label: t('Mitglieder') }]
      : []),
    ...(can(DEPT_PERM.membersView)
      ? [{ to: '/abteilung/entwicklung', label: t('Entwicklung') }]
      : []),
    ...(can(DEPT_PERM.invoicesView)
      ? [
          {
            to: can(DEPT_PERM.membersView) ? '/abteilung/rechnungen' : '/abteilung',
            label: t('Rechnungen'),
          },
        ]
      : []),
    ...(can(DEPT_PERM.rolesView) || can(DEPT_PERM.rolesManage)
      ? [{ to: '/abteilung/rollen', label: t('Rollen und Rechte') }]
      : []),
    ...(can(DEPT_PERM.entriesSubmit)
      ? [{ to: '/abteilung/meldungen', label: t('Meldungen') }]
      : []),
    ...(can(DEPT_PERM.export) ? [{ to: '/abteilung/export', label: t('Export') }] : []),
  ]
  return (
    <section>
      <div className="page-head">
        <h1>{dept.name}</h1>
        <p className="muted">
          {dept.label} · {dept.club_name}
        </p>
      </div>
      {tabs.length > 1 && <Tabs items={tabs} />}
      <Routes>
        <Route
          index
          element={
            !can(DEPT_PERM.membersView) && can(DEPT_PERM.invoicesView) ? (
              <DeptInvoices deptId={dept.id} />
            ) : (
              <DeptMemberList dept={dept} />
            )
          }
        />
        {can(DEPT_PERM.membersView) && (
          <Route
            path="entwicklung"
            element={
              <MemberDevelopment
                scope={`dept-${dept.id}`}
                load={(q) => statsApi.dept(dept.id, q)}
              />
            }
          />
        )}
        {can(DEPT_PERM.invoicesView) && (
          <Route path="rechnungen" element={<DeptInvoices deptId={dept.id} />} />
        )}
        <Route path="mitglied/:id" element={<DeptMemberPage dept={dept} />} />
        {(can(DEPT_PERM.rolesView) || can(DEPT_PERM.rolesManage)) && (
          <Route
            path="rollen"
            element={<DeptRolesPage dept={dept} canEdit={can(DEPT_PERM.rolesManage)} />}
          />
        )}
        {can(DEPT_PERM.export) && (
          <Route path="export" element={<ExportSection base={{ dept: dept.id }} />} />
        )}
        {can(DEPT_PERM.entriesSubmit) && (
          <Route path="meldungen/*" element={<DeptEntries deptId={dept.id} />} />
        )}
        <Route path="rundschreiben/*" element={<MovedCirculars />} />
        <Route
          path="*"
          element={<SubpageUnavailable to="/abteilung" label={t('Zur Übersicht')} />}
        />
      </Routes>
    </section>
  )
}

// Suche und Seite überstehen den Weg in die Akte und zurück (nur diese Sitzung, NMF-07)
const DEPT_LIST_KEY = (dept: number) => `hubiplan.abteilungsliste.${dept}`

function loadDeptList(dept: number): { term: string; page: number } {
  try {
    const raw = sessionStorage.getItem(DEPT_LIST_KEY(dept))
    if (raw) return JSON.parse(raw) as { term: string; page: number }
  } catch {
    // ohne Speicher geht es auch
  }
  return { term: '', page: 1 }
}

function DeptMemberList({ dept }: { dept: DeptSummary }) {
  const [initial] = useState(() => loadDeptList(dept.id))
  const [search, setSearch] = useState(initial.term)
  const [term, setTerm] = useState(initial.term)
  const [page, setPage] = useState(initial.page)
  const [data, setData] = useState<Page<MemberRow> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const query = `${term}|${page}`

  useEffect(() => {
    const tm = setTimeout(() => {
      if (search === term) return
      setTerm(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(tm)
  }, [search, term])

  useEffect(() => {
    try {
      sessionStorage.setItem(DEPT_LIST_KEY(dept.id), JSON.stringify({ term, page }))
    } catch {
      // ohne Speicher geht es auch
    }
  }, [dept.id, term, page])

  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let alive = true
    portalApi
      .deptMembers(dept.id, { suche: term, page })
      .then((d) => {
        if (alive) {
          setData(d)
          setError(null)
          setLoadedFor(`${term}|${page}`)
        }
      })
      .catch((err) => alive && setError(errorMessage(err)))
    return () => {
      alive = false
    }
  }, [dept.id, term, page, attempt])
  const stale = !!data && loadedFor !== query

  if (!dept.permissions.includes(DEPT_PERM.membersView)) {
    return (
      <div className="card empty-state">
        <p>{t('Deine Rolle darf die Mitgliederliste nicht sehen.')}</p>
      </div>
    )
  }

  const pages = data ? Math.max(1, Math.ceil(data.count / 50)) : 1
  return (
    <div className="card card-wide">
      {dept.permissions.includes(DEPT_PERM.cardsView) && (
        <div className="button-row">
          <a
            className="button button-ghost push-right"
            href={cardApi.deptPdfUrl(dept.id)}
            title={t('Ausweise mit QR-Code für alle Mitglieder (10 je A4-Seite)')}
          >
            {t('Ausweise aller Mitglieder (PDF)')}
          </a>
        </div>
      )}
      <input
        type="search"
        className="search-input"
        placeholder={t('Suchen: Name oder E-Mail')}
        aria-label={t('Mitglieder suchen')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {error && !data && <LoadError message={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {data && (
        <Freshness
          refreshing={stale && !error}
          error={error}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      )}
      {!data ? (
        !error && <p className="muted">{t('Lädt …')}</p>
      ) : data.results.length === 0 ? (
        <p className={`muted${stale ? ' is-stale' : ''}`}>{t('Keine Mitglieder gefunden.')}</p>
      ) : (
        <div className={stale ? 'is-stale' : undefined}>
          <p className="muted small">
            {data.count} {t('Mitglieder')}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>{t('Name')}</th>
                <th>{t('Geburtsdatum')}</th>
                <th>
                  <Term k="member_type">{t('Mitgliedsart')}</Term>
                </th>
                <th>{t('E-Mail')}</th>
                <th>{t('Telefon')}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/abteilung/mitglied/${r.id}`}>
                      {r.last_name}, {r.first_name}
                    </Link>
                  </td>
                  <td>{formatDate(r.birth_date)}</td>
                  <td>{r.member_type ?? '–'}</td>
                  <td>{r.email || '–'}</td>
                  <td>{r.phone || '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pages > 1 && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                {t('Zurück')}
              </button>
              <span className="muted small">
                {t('Seite {page} von', { page })} {pages}
              </span>
              <button
                type="button"
                className="button button-ghost"
                disabled={page >= pages}
                onClick={() => setPage(page + 1)}
              >
                {t('Weiter')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const CONTACT_KEYS = ['email', 'phone', 'street', 'postal_code', 'city', 'country'] as const

function memberValues(m: DeptMember) {
  return {
    last_name: m.last_name,
    first_name: m.first_name,
    birth_date: m.birth_date,
    email: m.contact?.email ?? '',
    phone: m.contact?.phone ?? '',
    street: m.contact?.street ?? '',
    postal_code: m.contact?.postal_code ?? '',
    city: m.contact?.city ?? '',
    country: m.contact?.country ?? '',
  }
}

function DeptMemberPage({ dept }: { dept: DeptSummary }) {
  const id = Number(useParams().id)
  const { data, error, setData } = useLoad(() => portalApi.deptMember(dept.id, id), [dept.id, id])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <p className="muted">{t('Lädt …')}</p>
  const canEdit = dept.permissions.includes(DEPT_PERM.membersEdit)
  const canAccess =
    dept.permissions.includes(DEPT_PERM.loginsView) ||
    dept.permissions.includes(DEPT_PERM.accessManage)
  return (
    <div className="stack">
      <p>
        <Link to="/abteilung">{t('← zur Liste')}</Link>
      </p>
      <DeptMemberForm
        key={data.id}
        dept={dept}
        member={data}
        canEdit={canEdit}
        onSaved={(m) => setData(m)}
      />
      {canAccess && (
        <AccessPanel
          access={data.access ?? null}
          hasEmail={!!data.contact?.email}
          contactEmail={data.contact?.email}
          canManage={dept.permissions.includes(DEPT_PERM.accessManage)}
          onSend={async (transfer) => {
            const r = await portalApi.sendDeptAccess(dept.id, id, transfer)
            setData({ ...data, access: r.access })
            return r
          }}
          onRemove={async () => {
            await portalApi.removeDeptAccess(dept.id, id)
            setData({ ...data, access: null })
          }}
        />
      )}
      {dept.permissions.includes(DEPT_PERM.cardsView) && (
        <CardPanel
          base={cardBase.dept(dept.id, id)}
          pdfUrl={cardApi.deptPdfUrl(dept.id, { mitglied: id })}
          canEdit={dept.permissions.includes(DEPT_PERM.cardsManage)}
        />
      )}
    </div>
  )
}

function DeptMemberForm({
  dept,
  member,
  canEdit,
  onSaved,
}: {
  dept: DeptSummary
  member: DeptMember
  canEdit: boolean
  onSaved: (m: DeptMember) => void
}) {
  const form = useForm(memberValues(member))
  const { values: v, errors, set } = form

  // Speichert automatisch; Kontaktdaten gehören zusammen und gehen gemeinsam raus
  const auto = useAutoSave(
    form,
    (changes, values) => {
      const payload: Record<string, string> = { ...changes }
      if (CONTACT_KEYS.some((k) => k in changes)) {
        for (const k of CONTACT_KEYS) payload[k] = values[k]
      }
      if (!payload.email) delete payload.email
      return portalApi.updateDeptMember(dept.id, member.id, payload)
    },
    { enabled: canEdit, onSaved: (saved) => onSaved(saved as DeptMember) },
  )

  return (
    <form className="card card-wide" onSubmit={(e: FormEvent) => e.preventDefault()}>
      <div className="card-head">
        <h2>
          {member.first_name} {member.last_name}
        </h2>
        {canEdit && <SaveStatus auto={auto} />}
      </div>
      <p className="muted small">
        {member.member_type ?? t('ohne Mitgliedsart')}
        {member.entry_date &&
          t(' · Mitglied seit {x}', {
            x: formatMemberDate(member.entry_date, dept.date_precision),
          })}
        {member.club_number && t(' · Nr. {club_number}', { club_number: member.club_number })}
        {member.departments.length > 0 && t(' · {x}', { x: member.departments.join(', ') })}
      </p>
      <fieldset disabled={!canEdit}>
        <div className="grid-3">
          <Field
            label={t('Name')}
            required
            value={v.last_name}
            error={errors.last_name}
            onChange={(e) => set('last_name', e.target.value)}
          />
          <Field
            label={t('Vorname')}
            required
            value={v.first_name}
            error={errors.first_name}
            onChange={(e) => set('first_name', e.target.value)}
          />
          <Field
            label={t('Geburtsdatum')}
            type="date"
            required
            value={v.birth_date}
            error={errors.birth_date}
            onChange={(e) => set('birth_date', e.target.value)}
          />
        </div>
        <div className="grid-3">
          {CONTACT_KEYS.map((key) => (
            <Field
              key={key}
              label={CONTACT_LABEL[key]}
              type={key === 'email' ? 'email' : 'text'}
              value={v[key]}
              error={errors[key]}
              onChange={(e) => set(key, e.target.value)}
            />
          ))}
        </div>
      </fieldset>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      {!canEdit && (
        <p className="muted small">{t('Deine Rolle darf die Daten ansehen, aber nicht ändern.')}</p>
      )}
    </form>
  )
}

const CONTACT_LABEL: Record<(typeof CONTACT_KEYS)[number], string> = {
  email: t('E-Mail'),
  phone: t('Telefon'),
  street: t('Straße und Hausnummer'),
  get postal_code() {
    return t('PLZ')
  },
  city: t('Ort'),
  country: t('Land'),
}

function DeptRolesPage({ dept, canEdit }: { dept: DeptSummary; canEdit: boolean }) {
  const roles = useLoad(() => portalApi.deptRoles(dept.id), [dept.id])
  const holders = useLoad(() => portalApi.holders(dept.id), [dept.id])
  const [error, setError] = useState<string | null>(null)
  const [newRole, setNewRole] = useState('')
  const sort = useSortable({
    items: roles.data?.roles ?? [],
    id: (r) => r.id,
    label: (r) => r.name,
    onReorder: (ids) => portalApi.reorderDeptRoles(dept.id, ids).then(() => roles.reload()),
    enabled: canEdit,
  })

  const loadError = roles.error ?? holders.error
  if (loadError) return <Alert kind="error">{loadError}</Alert>
  if (!roles.data || !holders.data) return <p className="muted">{t('Lädt …')}</p>
  const catalog = roles.data.catalog
  // Katalog mit Bereichen und Stufen; ältere Server liefern noch einzelne Rechte
  const staged = catalog.some((m) => m.kind === 'area')
  const perms = catalog.flatMap((m) => m.permissions)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await Promise.all([roles.reload(), holders.reload()])
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  function save(role: DeptRole, next: string[]) {
    void run(() => portalApi.updateDeptRole(dept.id, role.id, { permissions: next }))
  }

  function toggle(role: DeptRole, code: string, on: boolean) {
    save(role, on ? [...role.permissions, code] : role.permissions.filter((c) => c !== code))
  }

  return (
    <div className="stack">
      <div className="card card-wide">
        <h2>{t('Rollen und Rechte')}</h2>
        <p className="muted small">
          {t(
            'Hier legt ihr fest, was jede Rolle in der {label} darf. Rechte wirken für alle, die die Rolle innehaben und einen Zugang haben.',
            { label: dept.label },
          )}
        </p>
        {sort.active && <SortHint />}
        <ul className="role-list">
          {sort.ordered.map((r) => (
            <li
              key={r.id}
              ref={sort.rowProps(r).ref}
              className={['role-row', sort.rowProps(r).className].filter(Boolean).join(' ')}
            >
              {sort.handle(r)}
              <strong>
                {r.name}
                <span className="muted small">
                  {' · '}
                  {t('{n} vergeben', { n: r.holder_count })}
                </span>
              </strong>
              {staged ? (
                <div className="role-perms">
                  {r.permissions.length > 0 ? (
                    <PermissionSummary codes={r.permissions} catalog={catalog} />
                  ) : (
                    <p className="muted small">{t('keine (nur Amt)')}</p>
                  )}
                  <details>
                    <summary>{canEdit ? t('Rechte ändern') : t('Rechte ansehen')}</summary>
                    <PermissionMatrix
                      catalog={catalog}
                      codes={r.permissions}
                      readOnly={!canEdit}
                      onChange={(next) => save(r, next)}
                    />
                  </details>
                </div>
              ) : (
                <div className="role-perms">
                  {perms.map((p) => (
                    <Checkbox
                      key={p.code}
                      label={p.label}
                      checked={r.permissions.includes(p.code)}
                      disabled={!canEdit}
                      onChange={(on) => toggle(r, p.code, on)}
                    />
                  ))}
                </div>
              )}
              {canEdit && (
                <button
                  type="button"
                  className="link-button"
                  onClick={async () => {
                    if (!(await confirmRoleRemoval(r.name, r.holder_count))) return
                    try {
                      await portalApi.deleteDeptRole(dept.id, r.id)
                      await roles.reload()
                    } catch (err) {
                      await alertDialog({
                        title: t('Rolle nicht entfernt'),
                        message: errorMessage(err),
                      })
                    }
                  }}
                >
                  {t('Entfernen')}
                </button>
              )}
            </li>
          ))}
        </ul>
        {sort.status}
        {canEdit && (
          <form
            className="inline-add"
            onSubmit={(e) => {
              e.preventDefault()
              if (!newRole.trim()) return
              void run(() =>
                portalApi.createDeptRole(dept.id, { name: newRole.trim(), permissions: [] }),
              ).then(() => setNewRole(''))
            }}
          >
            <input
              aria-label={t('Neue Rolle')}
              placeholder={t('z. B. Kassierer')}
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
            />
            <button type="submit" className="button button-ghost">
              {t('Rolle hinzufügen')}
            </button>
          </form>
        )}
        {error && <Alert kind="error">{error}</Alert>}
      </div>
      <HoldersCard
        dept={dept}
        roles={roles.data.roles}
        holders={holders.data}
        onRun={run}
        canEdit={canEdit}
      />
    </div>
  )
}

function HoldersCard({
  dept,
  roles,
  holders,
  onRun,
  canEdit,
}: {
  dept: DeptSummary
  roles: DeptRole[]
  holders: Holder[]
  onRun: (action: () => Promise<unknown>) => Promise<void>
  canEdit: boolean
}) {
  const [assigning, setAssigning] = useState<UnitRole | null>(null)
  // Gleiche Ansicht wie unter Mitglieder › Ämter (Rollen-Vorschlag R3)
  const rows: UnitRole[] = roles.map((r) => ({
    id: r.id,
    name: r.name,
    holders: holders
      .filter((h) => h.role === r.id)
      .map((h) => ({
        id: h.id,
        membership: h.member_id,
        name: h.member_name,
        valid_from: h.valid_from,
      })),
  }))

  return (
    <div className="card card-wide">
      <h2>{t('Wer hat welche Rolle?')}</h2>
      <UnitRolesTable
        label={t('Heutige Inhaber')}
        roles={rows}
        canEdit={canEdit}
        onAssign={setAssigning}
        onEnd={(r, h) =>
          void confirmEndHolder(r, h).then((ok) => {
            if (ok) void onRun(() => portalApi.endHolder(dept.id, h.id))
          })
        }
      />
      {assigning && (
        <UnitRoleDialog
          orgId={0}
          role={assigning}
          search={(term) =>
            portalApi.deptMembers(dept.id, { suche: term, page_size: 20 }).then((p) => p.results)
          }
          submit={(d) =>
            portalApi.addHolder(dept.id, {
              member: d.member,
              role: d.role,
              valid_from: d.valid_from,
              end_previous: d.end_previous,
            })
          }
          onClose={() => setAssigning(null)}
          onDone={() => onRun(async () => undefined)}
        />
      )}
    </div>
  )
}
