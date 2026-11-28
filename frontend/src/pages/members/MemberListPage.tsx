import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { cardApi } from '../../api/cards.ts'
import { GENDERS, memberApi, memberName } from '../../api/members.ts'
import type { ListParams, MemberRow, Page } from '../../api/members.ts'
import { PERM, unitName } from '../../api/orgs.ts'
import { errorMessage, formatDate, formatMemberDate, useLoad } from '../../components/forms.ts'
import type { DatePrecision } from '../../components/forms.ts'
import { Freshness, LoadError, Loading } from '../../components/ui.tsx'
import { ExportPanel } from '../../components/ExportPanel.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { lang, t } from '../../i18n/index.ts'
import { atMost, BP_NARROW, BP_WIDE } from '../../theme/breakpoints.ts'
import { FilterChips } from '../../components/liste/FilterChips.tsx'
import type { ActiveFilter } from '../../components/liste/FilterChips.tsx'
import { SideSheet } from '../../components/liste/SideSheet.tsx'
import { ViewPicker } from '../../components/liste/ViewPicker.tsx'
import { rememberOrder } from '../../components/liste/recordOrder.ts'
import { PageNav } from '../../components/ListControls.tsx'
import { useDepartmentChoices, useMemberTypes } from '../../components/masterData.ts'

interface Column {
  key: string
  label: string
  value: (r: MemberRow, precision: DatePrecision) => string
  sort?: string
}

const COLUMNS: Column[] = [
  {
    key: 'member_type',
    label: t('Mitgliedsart'),
    value: (r) => r.member_type ?? '–',
    sort: 'art',
  },
  {
    key: 'birth_date',
    label: t('Geburtsdatum'),
    value: (r) =>
      !r.birth_date ? '–' : r.birth_year_only ? r.birth_date.slice(0, 4) : formatDate(r.birth_date),
    sort: 'geburtsdatum',
  },
  { key: 'gender', label: t('Geschlecht'), value: (r) => r.gender || '–' },
  {
    key: 'entry_date',
    label: t('Eintritt'),
    value: (r, p) => formatMemberDate(r.entry_date, p),
    sort: 'eintritt',
  },
  { key: 'exit_date', label: t('Austritt'), value: (r, p) => formatMemberDate(r.exit_date, p) },
  {
    key: 'club_number',
    label: t('Mitgliedsnr.'),
    value: (r) => r.club_number || '–',
    sort: 'nummer',
  },
  {
    key: 'member_number',
    label: t('Verbandsnr.'),
    value: (r) => (r.member_number ? String(r.member_number) : '–'),
  },
  {
    key: 'departments',
    label: t('Abteilung'),
    value: (r) => r.departments.join(', ') || '–',
    sort: 'abteilung',
  },
  {
    key: 'honorary_titles',
    label: t('Ehrungen'),
    value: (r) => (r.honorary_titles ?? []).join(', ') || '–',
    sort: 'ehrentitel',
  },
  { key: 'email', label: t('E-Mail'), value: (r) => r.email || '–' },
  { key: 'phone', label: t('Telefon'), value: (r) => r.phone || '–' },
  {
    key: 'address',
    label: t('Anschrift'),
    value: (r) =>
      [r.street, t('{postal_code} {city}', { postal_code: r.postal_code, city: r.city }).trim()]
        .filter(Boolean)
        .join(', ') || '–',
  },
]

const DEFAULT_COLUMNS = ['member_type', 'birth_date', 'entry_date', 'departments']
const COLUMN_KEY = 'hubiplan.mitgliederliste.spalten'

function loadColumns(): string[] {
  try {
    const raw = localStorage.getItem(COLUMN_KEY)
    return raw ? (JSON.parse(raw) as string[]) : DEFAULT_COLUMNS
  } catch {
    return DEFAULT_COLUMNS
  }
}

function saveColumns(cols: string[]) {
  try {
    localStorage.setItem(COLUMN_KEY, JSON.stringify(cols))
  } catch {
    // ohne Speicher geht es auch
  }
}

// Suche, Filter, Sortierung und Seite überstehen den Weg in die Akte und zurück
// (nur für diese Sitzung im Browser, nicht in der teilbaren Adresse).
const LIST_KEY = (org: number) => `hubiplan.mitgliederliste.${org}`
const STANDARD: ListParams = { status: 'aktiv', sortierung: 'name' }

function loadListState(org: number): ListParams | null {
  try {
    const raw = sessionStorage.getItem(LIST_KEY(org))
    return raw ? (JSON.parse(raw) as ListParams) : null
  } catch {
    return null
  }
}

export function MemberListPage() {
  const org = useActiveOrg()
  // Bezeichnung der Untereinheiten in der Sprache der Oberfläche (z. B. „Zug“ / „Platoon“)
  const terms = useTerms()
  const navigate = useNavigate()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const [params, setParams] = useState<ListParams>(
    () => loadListState(org.id) ?? { status: 'aktiv', sortierung: 'name', page: 1 },
  )
  const [search, setSearch] = useState(() => params.suche ?? '')
  useEffect(() => {
    try {
      sessionStorage.setItem(LIST_KEY(org.id), JSON.stringify(params))
    } catch {
      // ohne Speicher geht es auch
    }
  }, [org.id, params])
  const [columns, setColumns] = useState<string[]>(loadColumns)
  const [showFilters, setShowFilters] = useState(false)
  const [showColumns, setShowColumns] = useState(false)
  const [showExport, setShowExport] = useState(false)
  const canExport = org.permissions.includes(PERM.exportRun)
  const [data, setData] = useState<Page<MemberRow> | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Für welche Auswahl die angezeigten Treffer gelten (NMF-05)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const query = JSON.stringify(params)
  const types = useMemberTypes(org.id)
  const departments = useDepartmentChoices(org.id)
  // Mehrere Ebenen (z. B. Korps und Züge): Spalte und Filter nennen alle Bezeichnungen.
  const unitTerms = levelTerms(departments.data ?? [], terms)
  const awardsOn = org.modules.includes('awards')
  const titles = useLoad(
    () => (awardsOn ? memberApi.honoraryTitles(org.id, true) : Promise.resolve([])),
    [org.id, awardsOn],
  )
  const [defaultPageSize] = useState(() => (atMost(BP_NARROW) ? 10 : 50))
  const pageSize = [10, 20, 50].includes(params.page_size ?? 0)
    ? params.page_size!
    : defaultPageSize
  const filterCount = [
    params.status !== 'alle',
    params.art,
    params.geschlecht,
    params.typ,
    params.abteilung,
    params.ehrentitel,
    params.haushalt,
  ].filter(Boolean).length

  // Seitenblatt: auf breiten Bildschirmen zeigt ein Klick auf die Zeile das Mitglied daneben (W11)
  const [sheet, setSheet] = useState<MemberRow | null>(null)
  const closeSheet = useCallback(() => setSheet(null), [])
  const setFilter = (key: keyof ListParams, value: string) =>
    setParams((p) => ({ ...p, [key]: value, page: 1 }))
  // Gesetzte Filter als Chips (W11)
  const chips: ActiveFilter[] = []
  if (params.status !== 'aktiv')
    chips.push({
      key: 'status',
      label: params.status === 'ehemalig' ? t('ehemalige Mitglieder') : t('alle Mitglieder'),
      onRemove: () => setFilter('status', 'aktiv'),
    })
  if (params.art)
    chips.push({
      key: 'art',
      label: `${t('Mitgliedsart')}: ${types.data?.find((x) => String(x.id) === String(params.art))?.name ?? '…'}`,
      onRemove: () => setFilter('art', ''),
    })
  if (params.typ)
    chips.push({
      key: 'typ',
      label: params.typ === 'person' ? t('nur Personen') : t('nur Organisationen'),
      onRemove: () => setFilter('typ', ''),
    })
  if (params.geschlecht)
    chips.push({
      key: 'geschlecht',
      label: `${t('Geschlecht')}: ${
        params.geschlecht === 'ohne'
          ? t('ohne Angabe')
          : (GENDERS.find((g) => g.value === params.geschlecht)?.label ?? params.geschlecht)
      }`,
      onRemove: () => setFilter('geschlecht', ''),
    })
  if (params.abteilung) {
    const d = departments.data?.find((x) => String(x.id) === String(params.abteilung))
    chips.push({
      key: 'abteilung',
      label: `${unitTerms.Sg}: ${d ? unitName(d) : '…'}`,
      onRemove: () => setFilter('abteilung', ''),
    })
  }
  if (params.ehrentitel)
    chips.push({
      key: 'ehrentitel',
      label:
        params.ehrentitel === 'mit'
          ? t('mit Ehrung')
          : `${t('Ehrungen')}: ${titles.data?.find((x) => String(x.id) === String(params.ehrentitel))?.name ?? '…'}`,
      onRemove: () => setFilter('ehrentitel', ''),
    })
  if (params.haushalt)
    chips.push({
      key: 'haushalt',
      label:
        params.haushalt === 'mit'
          ? t('in einem Haushalt oder einer Firma')
          : t('ohne Haushalt und Firma'),
      onRemove: () => setFilter('haushalt', ''),
    })

  // Suche erst nach kurzer Tipp-Pause auslösen
  useEffect(() => {
    const tm = setTimeout(
      () => setParams((p) => ((p.suche ?? '') === search ? p : { ...p, suche: search, page: 1 })),
      300,
    )
    return () => clearTimeout(tm)
  }, [search])

  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let alive = true
    memberApi
      .list(org.id, { ...params, page_size: pageSize })
      .then((d) => {
        if (alive) {
          setData(d)
          setError(null)
          // Reihenfolge der Seite für „Vorheriges / Nächstes“ in der Akte (W12)
          rememberOrder(
            `mitglieder.${org.id}`,
            d.results.map((r) => r.id),
          )
          setLoadedFor(JSON.stringify(params))
        }
      })
      .catch((err) => alive && setError(errorMessage(err)))
    return () => {
      alive = false
    }
  }, [org.id, params, pageSize, attempt])
  const stale = !!data && loadedFor !== query

  function toggleColumn(key: string, on: boolean) {
    const next = on ? [...columns, key] : columns.filter((c) => c !== key)
    setColumns(next)
    saveColumns(next)
  }

  function sortBy(key: string) {
    setParams((p) => ({ ...p, sortierung: p.sortierung === key ? `-${key}` : key, page: 1 }))
  }

  // Spalte „Ehrungen“ nur mit Modul Ehrungen & Jubiläen
  const choosable = COLUMNS.filter((c) => c.key !== 'honorary_titles' || awardsOn)
  const visible = choosable.filter((c) => columns.includes(c.key))
  const pages = data ? Math.max(1, Math.ceil(data.count / pageSize)) : 1
  const pagination = pages > 1 && (
    <PageNav
      prevDisabled={stale || (params.page ?? 1) <= 1}
      nextDisabled={stale || (params.page ?? 1) >= pages}
      onPrev={() => setParams((p) => ({ ...p, page: (p.page ?? 1) - 1 }))}
      onNext={() => setParams((p) => ({ ...p, page: (p.page ?? 1) + 1 }))}
    >
      {t('Seite {page} von', { page: params.page ?? 1 })} {pages}
    </PageNav>
  )
  // Pfeil nur fürs Auge; Screenreader bekommen die Richtung über aria-sort (WCAG 1.3.1)
  const sortMark = (key: string) =>
    params.sortierung === key || params.sortierung === `-${key}` ? (
      <span aria-hidden="true">{params.sortierung === key ? ' ▲' : ' ▼'}</span>
    ) : null
  const ariaSort = (key: string) =>
    params.sortierung === key
      ? ('ascending' as const)
      : params.sortierung === `-${key}`
        ? ('descending' as const)
        : undefined

  return (
    <section className="member-list-page">
      <PageHeader
        primary={canEdit ? { label: t('Mitglied aufnehmen'), to: '/mitglieder/neu' } : null}
        actions={[
          canExport && { label: t('Export'), onClick: () => setShowExport((s) => !s) },
          org.permissions.includes(PERM.cardsView) && {
            label: t('Ausweise (PDF)'),
            hint: t(
              'Ausweise mit QR-Code für alle aktuellen Mitglieder der Auswahl (10 je A4-Seite)',
            ),
            href: cardApi.orgPdfUrl(org.id, {
              suche: params.suche,
              art: params.art,
              geschlecht: params.geschlecht,
              typ: params.typ,
              abteilung: params.abteilung,
              ehrentitel: params.ehrentitel,
              sortierung: params.sortierung,
            }),
          },
        ]}
      />

      <div className="card card-wide filters">
        <input
          type="search"
          className="search-input"
          placeholder={t('Suchen')}
          aria-label={t('Mitglieder suchen')}
          aria-describedby="member-search-hint"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {/* Kurzer Platzhalter, Erklärung als Hilfetext: bricht um, statt gekürzt zu werden (VW-45) */}
        <p id="member-search-hint" className="filters-hint muted small">
          {t('Sucht nach Name, E-Mail, Mitglieds- oder Verbandsnummer.')}
        </p>
        <button
          type="button"
          className="button button-ghost member-mobile-toggle"
          aria-expanded={showFilters}
          aria-controls="member-filter-options"
          onClick={() => setShowFilters((v) => !v)}
        >
          {t('Filter ({count})', { count: filterCount })}
        </button>
        <span className="member-mobile-toggle muted small">
          {params.status === 'ehemalig'
            ? t('ehemalige Mitglieder')
            : params.status === 'alle'
              ? t('alle Mitglieder')
              : t('aktuelle Mitglieder')}
        </span>
        <div
          id="member-filter-options"
          className={`member-filter-options${showFilters ? ' is-expanded' : ''}`}
        >
          <select
            aria-label={t('Status')}
            value={params.status}
            onChange={(e) => setParams((p) => ({ ...p, status: e.target.value, page: 1 }))}
          >
            <option value="aktiv">{t('aktuelle Mitglieder')}</option>
            <option value="ehemalig">{t('ehemalige Mitglieder')}</option>
            <option value="alle">{t('alle')}</option>
          </select>
          <select
            aria-label={t('Mitgliedsart')}
            value={params.art ?? ''}
            onChange={(e) => setParams((p) => ({ ...p, art: e.target.value, page: 1 }))}
          >
            <option value="">{t('alle Mitgliedsarten')}</option>
            {types.data?.map((tm) => (
              <option key={tm.id} value={tm.id}>
                {tm.name}
              </option>
            ))}
          </select>
          <select
            aria-label={t('Mitgliedstyp')}
            value={params.typ ?? ''}
            onChange={(e) => setParams((p) => ({ ...p, typ: e.target.value, page: 1 }))}
          >
            <option value="">{t('Personen und Organisationen')}</option>
            <option value="person">{t('nur Personen')}</option>
            <option value="organisation">{t('nur Organisationen')}</option>
          </select>
          <select
            aria-label={t('Geschlecht')}
            value={params.geschlecht ?? ''}
            onChange={(e) => setParams((p) => ({ ...p, geschlecht: e.target.value, page: 1 }))}
          >
            <option value="">{t('alle Geschlechter')}</option>
            {GENDERS.filter((g) => g.value).map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
            <option value="ohne">{t('ohne Angabe')}</option>
          </select>
          {departments.data && departments.data.length > 0 && (
            <select
              aria-label={unitTerms.Sg}
              value={params.abteilung ?? ''}
              onChange={(e) => setParams((p) => ({ ...p, abteilung: e.target.value, page: 1 }))}
            >
              <option value="">{t('alle {pl}', { pl: unitTerms.pl })}</option>
              {departments.data.map((d) => (
                <option key={d.id} value={d.id}>
                  {unitName(d)}
                </option>
              ))}
            </select>
          )}
          {titles.data && titles.data.length > 0 && (
            <select
              aria-label={t('Ehrungen')}
              value={params.ehrentitel ?? ''}
              onChange={(e) => setParams((p) => ({ ...p, ehrentitel: e.target.value, page: 1 }))}
            >
              <option value="">{t('alle (mit und ohne Ehrung)')}</option>
              <option value="mit">{t('mit Ehrung')}</option>
              {titles.data.map((tm) => (
                <option key={tm.id} value={tm.id}>
                  {tm.own
                    ? tm.name
                    : t('{name} ({owner_name})', { name: tm.name, owner_name: tm.owner_name })}
                  {tm.is_archived ? t(' (archiviert)') : ''}
                </option>
              ))}
            </select>
          )}
          {org.type === 'club' && (
            <select
              aria-label={t('Haushalt')}
              value={params.haushalt ?? ''}
              onChange={(e) => setParams((p) => ({ ...p, haushalt: e.target.value, page: 1 }))}
            >
              <option value="">{t('mit und ohne Haushalt')}</option>
              <option value="mit">{t('in einem Haushalt oder einer Firma')}</option>
              <option value="ohne">{t('ohne Haushalt und Firma')}</option>
            </select>
          )}
          <button
            type="button"
            className="button button-ghost"
            aria-expanded={showColumns}
            aria-controls="member-column-options"
            onClick={() => setShowColumns((s) => !s)}
          >
            {t('Spalten')}
          </button>
          {showColumns && (
            <div className="column-picker" id="member-column-options">
              {choosable.map((c) => (
                <label key={c.key} className="checkbox">
                  <input
                    type="checkbox"
                    checked={columns.includes(c.key)}
                    onChange={(e) => toggleColumn(c.key, e.target.checked)}
                  />
                  <span>{c.key === 'departments' ? unitTerms.Sg : c.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="list-tools">
        <FilterChips
          filters={chips}
          onClearAll={() =>
            setParams((p) => ({
              ...p,
              ...STANDARD,
              art: '',
              typ: '',
              geschlecht: '',
              abteilung: '',
              ehrentitel: '',
              haushalt: '',
              page: 1,
            }))
          }
        />
        <ViewPicker
          list={`mitglieder.${org.id}`}
          current={{ ...params, page: undefined, page_size: undefined }}
          standard={STANDARD}
          onApply={(v) => {
            setParams({ ...STANDARD, ...v, page: 1, page_size: params.page_size })
            setSearch(v.suche ?? '')
          }}
        />
      </div>

      {showExport && (
        <ExportPanel
          orgId={org.id}
          kind="members"
          filters={{ ...params, page: undefined }}
          onClose={() => setShowExport(false)}
        />
      )}
      {error && !data && <LoadError message={error} onRetry={() => setAttempt((n) => n + 1)} />}
      {data && (
        <Freshness
          refreshing={stale && !error}
          error={error}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      )}
      {!data ? (
        !error && <Loading />
      ) : (
        <div className={`card card-wide${stale ? ' is-stale' : ''}`}>
          <div className="member-results-toolbar">
            <p className="muted small">
              {data.count} {data.count === 1 ? t('Mitglied') : t('Mitglieder')}
            </p>
            <label className="member-page-size small">
              {t('Pro Seite')}
              <select
                value={pageSize}
                onChange={(e) =>
                  setParams((p) => ({ ...p, page_size: Number(e.target.value), page: 1 }))
                }
              >
                {[10, 20, 50].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            {pagination}
          </div>
          {data.count === 0 ? (
            <p className="muted">{t('Keine Mitglieder gefunden.')}</p>
          ) : (
            <table className="table table-keep member-table">
              <thead>
                <tr>
                  <th aria-sort={ariaSort('name')}>
                    <button type="button" className="th-sort" onClick={() => sortBy('name')}>
                      {t('Name')}
                      {sortMark('name')}
                    </button>
                  </th>
                  {visible.map((c) => (
                    <th
                      key={c.key}
                      className={c.key === 'member_type' ? '' : 'col-optional'}
                      aria-sort={c.sort ? ariaSort(c.sort) : undefined}
                    >
                      {c.sort ? (
                        <button type="button" className="th-sort" onClick={() => sortBy(c.sort!)}>
                          {c.key === 'departments' ? unitTerms.Sg : c.label}
                          {sortMark(c.sort)}
                        </button>
                      ) : c.key === 'departments' ? (
                        unitTerms.Sg
                      ) : (
                        c.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.results.map((r) => (
                  <tr
                    key={r.id}
                    className={`clickable${r.status === 'former' ? ' inactive' : ''}${sheet?.id === r.id ? ' is-selected' : ''}`}
                    onClick={() =>
                      atMost(BP_WIDE) ? navigate(`/mitglieder/${r.id}`) : setSheet(r)
                    }
                  >
                    <td className="name-cell">
                      {r.photo_url ? (
                        <img src={r.photo_url} alt="" className="member-avatar" loading="lazy" />
                      ) : (
                        <span className="member-avatar member-avatar-empty" aria-hidden="true">
                          {r.kind === 'organization'
                            ? r.last_name.charAt(0)
                            : `${r.first_name.charAt(0)}${r.last_name.charAt(0)}`}
                        </span>
                      )}
                      <Link to={`/mitglieder/${r.id}`} onClick={(e) => e.stopPropagation()}>
                        {memberName(r)}
                      </Link>
                      {r.kind === 'organization' && (
                        <span className="muted small"> · {t('Organisation')}</span>
                      )}
                    </td>
                    {visible.map((c) => (
                      <td key={c.key} className={c.key === 'member_type' ? '' : 'col-optional'}>
                        {c.value(r, org.date_precision)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {pagination}
        </div>
      )}
      {sheet && (
        <SideSheet
          title={memberName(sheet)}
          subtitle={[sheet.member_type, sheet.status === 'former' ? t('ehemalig') : null]
            .filter(Boolean)
            .join(' · ')}
          onClose={closeSheet}
          actions={
            <Link className="button button-primary" to={`/mitglieder/${sheet.id}`}>
              {t('Akte öffnen')}
            </Link>
          }
        >
          <MemberSheet row={sheet} precision={org.date_precision} unitLabel={unitTerms.Sg} />
        </SideSheet>
      )}
    </section>
  )
}

/** Inhalt des Seitenblatts: was die Liste über das Mitglied schon weiß, ohne neue Abfrage. */
function MemberSheet({
  row,
  precision,
  unitLabel,
}: {
  row: MemberRow
  precision: DatePrecision
  unitLabel: string
}) {
  const address = [row.street, [row.postal_code, row.city].filter(Boolean).join(' ')]
    .filter(Boolean)
    .join(', ')
  const facts: [string, ReactNode][] = []
  const col = (key: string) => COLUMNS.find((c) => c.key === key)!
  if (row.member_number != null) facts.push([t('Mitgliedsnummer'), row.member_number])
  for (const key of ['birth_date', 'entry_date', 'exit_date'] as const)
    if (row[key]) facts.push([col(key).label, col(key).value(row, precision)])
  if (row.departments.length) facts.push([unitLabel, row.departments.join(', ')])
  if (row.households?.length)
    facts.push([t('Haushalt'), row.households.map((h) => h.name).join(', ')])
  if (row.honorary_titles.length) facts.push([t('Ehrungen'), row.honorary_titles.join(', ')])
  if (row.email)
    facts.push([
      t('E-Mail'),
      <a key="mail" href={`mailto:${row.email}`}>
        {row.email}
      </a>,
    ])
  if (row.phone)
    facts.push([
      t('Telefon'),
      <a key="tel" href={`tel:${row.phone}`}>
        {row.phone}
      </a>,
    ])
  if (address) facts.push([t('Anschrift'), address])
  return (
    <dl className="side-sheet-facts">
      {facts.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function levelTerms(
  rows: {
    label?: string
    label_plural?: string
    label_en?: string
    label_plural_en?: string
    depth?: number
  }[],
  terms: Record<string, string>,
): { Sg: string; pl: string } {
  const en = lang() === 'en'
  const sg: string[] = []
  const pl: string[] = []
  for (const d of [...rows].sort((a, b) => (a.depth ?? 0) - (b.depth ?? 0))) {
    const one = (en && d.label_en) || d.label
    if (!one || sg.includes(one)) continue
    sg.push(one)
    pl.push((en && d.label_plural_en) || d.label_plural || one)
  }
  if (sg.length < 2) return { Sg: terms.Sg, pl: terms.pl }
  return { Sg: sg.join(' / '), pl: pl.join(' / ') }
}
