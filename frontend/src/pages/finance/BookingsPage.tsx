// Kasse: Buchungen erfassen, suchen und mit Belegen versehen.
import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { Fragment, useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { FilterChips } from '../../components/liste/FilterChips.tsx'
import type { ActiveFilter } from '../../components/liste/FilterChips.tsx'
import { ViewPicker } from '../../components/liste/ViewPicker.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { financeApi } from '../../api/finance.ts'
import type { Booking, BookingFilter, BookingKind } from '../../api/finance.ts'
import { orgApi, PERM } from '../../api/orgs.ts'
import { errorMessage, useLoad, useQueryLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { MfaBookingNotice, useBookingPaused } from '../../components/MfaBookingNotice.tsx'
import { PageActions } from '../../components/PageHeader.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { Term } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { PageNav } from '../../components/ListControls.tsx'
import { SuggestInput } from '../../components/SuggestInput.tsx'
import {
  useFinanceAccounts,
  useFinanceCategories,
  useFinanceSettings,
} from '../../components/masterData.ts'
import { BookingForm } from './BookingForm.tsx'
import { KIND_LABEL } from './bookingsHelpers.ts'
import { BookingRow } from './BookingRow.tsx'

const KIND_PARAM: Record<BookingKind, string> = {
  income: 'einnahme',
  expense: 'ausgabe',
  transfer: 'umbuchung',
}
const NEW_KIND: Record<string, BookingKind> = {
  einnahme: 'income',
  ausgabe: 'expense',
  umbuchung: 'transfer',
}

export function BookingsPage() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  // Ohne Zwei-Faktor-Anmeldung zieht der Server das Recht zu buchen ab: Grund nennen, statt
  // die Seite nur als „nur lesen“ zu zeigen
  const paused = useBookingPaused() && !canEdit
  const [params, setParams] = useSearchParams()
  const settings = useFinanceSettings(org.id)
  const accounts = useFinanceAccounts(org.id)
  const categories = useFinanceCategories(org.id)
  const projects = useLoad(() => financeApi.projects(org.id), [org.id])
  const departments = useLoad(
    () => (org.type === 'club' ? orgApi.departmentChoices(org.id) : Promise.resolve([])),
    [org.id, org.type],
  )
  const partners = useLoad(() => financeApi.counterparties(org.id), [org.id])
  const [search, setSearch] = useState(params.get('suche') ?? '')
  const [partner, setPartner] = useState(params.get('partner') ?? '')
  const [error, setError] = useState<string | null>(null)
  // Geöffnete Buchung in der Adresse: ?buchung=12 bzw. ?buchung=neu-ausgabe
  const detail = useDetailParam('buchung')
  const [loaded, setLoaded] = useState<Booking | null>(null)
  const [missing, setMissing] = useState<string | null>(null)
  const openedId = detail.value && /^\d+$/.test(detail.value) ? Number(detail.value) : null
  const newKind = detail.value?.startsWith('neu-') ? NEW_KIND[detail.value.slice(4)] : undefined
  const [version, setVersion] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)

  const year = params.get('jahr') ?? (settings.data ? String(settings.data.current_year) : '')
  const filter: BookingFilter = {
    jahr: year,
    konto: params.get('konto') ?? '',
    kategorie: params.get('kategorie') ?? '',
    art: params.get('art') ?? '',
    bereich: params.get('bereich') ?? '',
    suche: params.get('suche') ?? '',
    partner: params.get('partner') ?? '',
    ohne_beleg: params.get('ohne_beleg') === '1',
    veranstaltung: params.get('veranstaltung') ?? '',
    page: Number(params.get('seite') ?? 1),
  }
  const filterKey = JSON.stringify(filter)

  const {
    data,
    error: queryError,
    reload,
  } = useQueryLoad(
    () => financeApi.bookings(org.id, JSON.parse(filterKey) as BookingFilter),
    [org.id, filterKey, version],
    !!year && search === filter.suche && partner.trim() === filter.partner,
  )
  const editing: Booking | BookingKind | null =
    newKind ??
    (openedId !== null
      ? (data?.results.find((b) => b.id === openedId) ?? (loaded?.id === openedId ? loaded : null))
      : null)
  function setEditing(b: Booking | BookingKind | null, replace = false) {
    if (b === null) return detail.close()
    if (typeof b !== 'string') setLoaded(b)
    const v = typeof b === 'string' ? `neu-${KIND_PARAM[b]}` : String(b.id)
    if (replace) detail.replace(v)
    else detail.open(v)
  }

  // Gesetzte Filter als Chips und gemerkte Ansichten (Web-Oberfläche, Listen-Bausteine);
  // das Geschäftsjahr bleibt außen vor, damit eine Ansicht in jedem Jahr passt
  const FILTER_KEYS = [
    'suche',
    'partner',
    'konto',
    'kategorie',
    'art',
    'bereich',
    'veranstaltung',
    'ohne_beleg',
  ] as const
  const filterParams: Record<string, string> = Object.fromEntries(
    FILTER_KEYS.map((k) => [k, params.get(k) ?? '']),
  )
  function applyFilters(v: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const k of FILTER_KEYS) {
      if (v[k]) next.set(k, v[k])
      else next.delete(k)
    }
    next.delete('seite')
    setParams(next, { replace: true })
    setSearch(v.suche ?? '')
    setPartner(v.partner ?? '')
  }
  const remove = (key: string) => () => applyFilters({ ...filterParams, [key]: '' })
  const chips: ActiveFilter[] = []
  if (filter.suche)
    chips.push({ key: 'suche', label: `${t('Suche')}: ${filter.suche}`, onRemove: remove('suche') })
  if (filter.partner)
    chips.push({
      key: 'partner',
      label: `${t('Empfänger/Zahler')}: ${filter.partner}`,
      onRemove: remove('partner'),
    })
  if (filter.konto)
    chips.push({
      key: 'konto',
      label: `${t('Konto')}: ${accounts.data?.find((a) => String(a.id) === filter.konto)?.name ?? '…'}`,
      onRemove: remove('konto'),
    })
  if (filter.kategorie)
    chips.push({
      key: 'kategorie',
      label: `${t('Kategorie')}: ${categories.data?.find((c) => String(c.id) === filter.kategorie)?.name ?? '…'}`,
      onRemove: remove('kategorie'),
    })
  if (filter.art)
    chips.push({
      key: 'art',
      label: `${t('Art')}: ${KIND_LABEL[filter.art as BookingKind] ?? filter.art}`,
      onRemove: remove('art'),
    })
  if (filter.bereich)
    chips.push({
      key: 'bereich',
      label:
        filter.bereich === '-'
          ? `${t('steuerlicher Bereich')}: ${t('ohne Zuordnung')}`
          : `${t('steuerlicher Bereich')}: ${settings.data?.tax_areas.find((a) => a.value === filter.bereich)?.label ?? filter.bereich}`,
      onRemove: remove('bereich'),
    })
  if (filter.veranstaltung)
    chips.push({
      key: 'veranstaltung',
      label:
        filter.veranstaltung === '-'
          ? t('ohne Veranstaltung')
          : `${t('Veranstaltung')}: ${projects.data?.find((p) => String(p.id) === filter.veranstaltung)?.name ?? '…'}`,
      onRemove: remove('veranstaltung'),
    })
  if (filter.ohne_beleg)
    chips.push({ key: 'ohne_beleg', label: t('ohne Beleg'), onRemove: remove('ohne_beleg') })

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    // Neue Filter beginnen auf Seite 1; Blättern selbst behält die Seite
    if (key !== 'seite') next.delete('seite')
    setParams(next, { replace: true })
  }

  useEffect(() => {
    const tm = setTimeout(() => {
      if ((params.get('suche') ?? '') !== search) setFilter('suche', search)
    }, 300)
    return () => clearTimeout(tm)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  useEffect(() => {
    const tm = setTimeout(() => {
      if ((params.get('partner') ?? '') !== partner.trim()) setFilter('partner', partner.trim())
    }, 400)
    return () => clearTimeout(tm)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [partner])

  // Direkt aufgerufene Buchung (Link, Neuladen), die nicht auf der aktuellen Seite steht
  useEffect(() => {
    if (openedId === null || loaded?.id === openedId) return
    if (data?.results.some((b) => b.id === openedId)) return
    let alive = true
    financeApi
      .booking(org.id, openedId)
      .then((b) => {
        if (alive) {
          setLoaded(b)
          setMissing(null)
        }
      })
      .catch((err) => alive && setMissing(errorMessage(err)))
    return () => {
      alive = false
    }
  }, [org.id, openedId, loaded, data])

  const loadError = settings.error ?? accounts.error ?? categories.error
  const baseError = loadError ? (
    <LoadError
      message={loadError}
      onRetry={() => {
        if (settings.error) void settings.reload()
        if (accounts.error) void accounts.reload()
        if (categories.error) void categories.reload()
      }}
    />
  ) : null
  if (baseError && (!settings.data || !accounts.data || !categories.data)) return baseError
  if (!settings.data || !accounts.data || !categories.data) return <Loading />

  const refresh = () => {
    setError(null)
    setVersion((v) => v + 1)
    void accounts.reload()
    void partners.reload()
  }
  const pages = data ? Math.max(1, Math.ceil(data.count / 100)) : 1

  if (accounts.data.length === 0) {
    // Ohne zweiten Faktor lässt sich auch kein Konto anlegen: zuerst dorthin führen
    if (paused) return <MfaBookingNotice />
    return (
      <div className="card empty-state">
        <p>
          {t('Zum Buchen muss zuerst ein Konto eingerichtet werden:')}{' '}
          <Link to="/finanzen/einrichtung/konten">{t('Finanzen → Einrichtung → Konten')}</Link>.
        </p>
      </div>
    )
  }

  async function renumber() {
    const label = settings.data!.years.find((y) => String(y.year) === year)?.label
    if (
      await confirmDialog({
        title: t('Buchungen neu nummerieren?'),
        message: t('Alle Buchungen im Geschäftsjahr {x} werden nach Datum neu durchnummeriert.', {
          x: label ?? year,
        }),
        confirmLabel: t('Neu nummerieren'),
        danger: false,
      })
    ) {
      financeApi
        .renumber(org.id, Number(year))
        .then((r) => {
          setNotice(t('{changed} Buchungsnummern geändert.', { changed: r.changed }))
          refresh()
        })
        .catch((err) => setError(errorMessage(err)))
    }
  }

  return (
    <div className="stack">
      {baseError}
      {/* Seitenkopf (S-05, W-14): ein Knopf „Neue Buchung“ mit Auswahl, Sammelaktion im Menü */}
      <PageActions
        primary={
          canEdit && editing === null
            ? {
                label: t('Neue Buchung'),
                items: [
                  { label: t('Einnahme'), onClick: () => setEditing('income') },
                  { label: t('Ausgabe'), onClick: () => setEditing('expense') },
                  { label: t('Umbuchung'), onClick: () => setEditing('transfer') },
                ],
              }
            : null
        }
        actions={[
          canEdit &&
            !!year &&
            year !== 'alle' && { label: t('Neu nummerieren'), onClick: () => void renumber() },
        ]}
      />
      {paused && <MfaBookingNotice />}
      {openedId !== null && editing === null && missing && (
        <Alert kind="error">
          {t('Die Buchung lässt sich nicht öffnen:')} {missing}
        </Alert>
      )}
      {editing !== null && (
        <EditAt at={typeof editing === 'string' ? null : editKey('booking', editing.id)}>
          <BookingForm
            key={typeof editing === 'string' ? `${editing}-${version}` : editing.id}
            orgId={org.id}
            isClub={org.type === 'club'}
            hasMembers={org.modules.includes('members')}
            booking={typeof editing === 'string' ? null : editing}
            kind={typeof editing === 'string' ? editing : editing.kind}
            accounts={accounts.data}
            categories={categories.data}
            departments={departments.data ?? []}
            projects={projects.data ?? []}
            vatRegistered={!!settings.data?.vat_registered}
            canEdit={canEdit}
            onSaved={(b, again) => {
              refresh()
              if (again) setVersion((v) => v + 1)
              setEditing(again ? b.kind : b, true)
            }}
            onClose={() => {
              setEditing(null)
              refresh()
            }}
          />
        </EditAt>
      )}

      <div className="card card-wide filters">
        <input
          type="search"
          className="search-input"
          placeholder={t('Suchen: Text, Empfänger/Zahler, Belegnummer, Betrag oder Nummer')}
          aria-label={t('Buchungen suchen')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SuggestInput
          type="search"
          suggestions={(partners.data ?? []).map((p) => ({ value: p.name }))}
          placeholder={t('Empfänger/Zahler')}
          aria-label={t('Empfänger/Zahler')}
          value={partner}
          onChange={(e) => setPartner(e.target.value)}
        />
        <select
          aria-label={t('Geschäftsjahr')}
          value={year}
          onChange={(e) => setFilter('jahr', e.target.value)}
        >
          {settings.data.years.map((y) => (
            <option key={y.year} value={y.year}>
              {y.label}
            </option>
          ))}
          <option value="alle">{t('alle Jahre')}</option>
        </select>
        <select
          aria-label={t('Konto')}
          value={filter.konto}
          onChange={(e) => setFilter('konto', e.target.value)}
        >
          <option value="">{t('alle Konten')}</option>
          {accounts.data.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <select
          aria-label={t('Kategorie')}
          value={filter.kategorie}
          onChange={(e) => setFilter('kategorie', e.target.value)}
        >
          <option value="">{t('alle Kategorien')}</option>
          {categories.data.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          aria-label={t('Art')}
          value={filter.art}
          onChange={(e) => setFilter('art', e.target.value)}
        >
          <option value="">{t('alle Arten')}</option>
          {Object.entries(KIND_LABEL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        {settings.data.tax_areas_enabled && (
          <select
            aria-label={t('steuerlicher Bereich')}
            value={filter.bereich}
            onChange={(e) => setFilter('bereich', e.target.value)}
          >
            <option value="">{t('alle Bereiche')}</option>
            {settings.data.tax_areas.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
            <option value="-">{t('ohne Zuordnung')}</option>
          </select>
        )}
        {(projects.data?.length ?? 0) > 0 && (
          <select
            aria-label={t('Veranstaltung')}
            value={filter.veranstaltung}
            onChange={(e) => setFilter('veranstaltung', e.target.value)}
          >
            <option value="">{t('alle Veranstaltungen')}</option>
            <option value="-">{t('ohne Veranstaltung')}</option>
            {projects.data!.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={filter.ohne_beleg}
            onChange={(e) => setFilter('ohne_beleg', e.target.checked ? '1' : '')}
          />
          <span>{t('ohne Beleg')}</span>
        </label>
      </div>

      <div className="list-tools">
        <FilterChips filters={chips} onClearAll={() => applyFilters({})} />
        <ViewPicker
          list={`kassenbuch.${org.id}`}
          current={filterParams}
          standard={{}}
          onApply={applyFilters}
        />
      </div>

      <div className="card card-wide">
        {error && <Alert kind="error">{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        {queryError && <LoadError message={queryError} onRetry={() => void reload()} />}
        {!data ? (
          !queryError && (
            <p className="muted" role="status">
              {t('Wird geladen …')}
            </p>
          )
        ) : data.results.length === 0 ? (
          <p className="muted">{t('Keine Buchungen gefunden.')}</p>
        ) : (
          <>
            <p className="muted small">
              {data.count} {t('Buchungen')}
            </p>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Nr.')}</th>
                    <th>{t('Datum')}</th>
                    <th>{t('Text')}</th>
                    <th>{t('Konto')}</th>
                    <th>{t('Kategorie')}</th>
                    <th className="num">{t('Betrag')}</th>
                    <th>
                      <Term k="receipt">{t('Beleg')}</Term>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((b) => (
                    <Fragment key={b.id}>
                      <BookingRow
                        booking={b}
                        account={filter.konto ? Number(filter.konto) : null}
                        onOpen={() => setEditing(b)}
                      />
                      <EditSlot id={editKey('booking', b.id)} colSpan={7} />
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <PageNav
                prevDisabled={filter.page! <= 1}
                nextDisabled={filter.page! >= pages}
                onPrev={() => setFilter('seite', filter.page! > 2 ? String(filter.page! - 1) : '')}
                onNext={() => setFilter('seite', String(filter.page! + 1))}
              >
                {t('Seite {page} von', { page: filter.page })} {pages}
              </PageNav>
            )}
          </>
        )}
      </div>
    </div>
  )
}
