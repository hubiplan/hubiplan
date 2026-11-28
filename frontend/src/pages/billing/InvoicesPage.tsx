// Beiträge: Rechnungen suchen, ansehen, einzeln anlegen, Zahlungen erfassen.
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FilterChips } from '../../components/liste/FilterChips.tsx'
import type { ActiveFilter } from '../../components/liste/FilterChips.tsx'
import { ViewPicker } from '../../components/liste/ViewPicker.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { billingApi } from '../../api/billing.ts'
import { euro } from '../../api/finance.ts'
import { formatDate, useLoad, useQueryLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { useTerms } from '../../org/terms.ts'
import { Term } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { PageNav } from '../../components/ListControls.tsx'
import { useBillingSettings } from '../../components/masterData.ts'
import { hasMembersModule } from './invoicesHelpers.ts'
import { StatusBadge } from './StatusBadge.tsx'
import { InvoiceDetail } from './InvoiceDetail.tsx'
import { InvoiceForm } from './InvoiceForm.tsx'

export function InvoicesPage() {
  const tm = useTerms()
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const settings = useBillingSettings(org.id)
  // Untereinheiten haben keine Beitragsläufe
  const runs = useLoad(
    () => (org.type === 'unit' ? Promise.resolve([]) : billingApi.runs(org.id)),
    [org.id, org.type],
  )
  const [search, setSearch] = useState(params.get('suche') ?? '')
  const detail = useDetailParam('rechnung')
  const creating = detail.value === 'neu'
  const openId = detail.value && /^\d+$/.test(detail.value) ? Number(detail.value) : null
  const [version, setVersion] = useState(0)

  const status = params.get('status') ?? ''
  const run = params.get('lauf') ?? ''
  const overdue = params.get('ueberfaellig') === '1'
  const term = params.get('suche') ?? ''
  const page = Number(params.get('seite') ?? '1')
  const club = params.get('verein') ?? ''
  const project = params.get('veranstaltung') ?? ''

  const { data, error, reload } = useQueryLoad(
    () =>
      billingApi.invoices(org.id, {
        status,
        lauf: run,
        suche: term,
        ueberfaellig: overdue,
        verein: club,
        veranstaltung: project,
        page,
      }),
    [org.id, status, run, term, overdue, club, project, page, version],
  )

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('seite')
    setParams(next)
  }

  // Gesetzte Filter als Chips und gemerkte Ansichten (Web-Oberfläche, Listen-Bausteine)
  const filterParams = {
    suche: term,
    status,
    ueberfaellig: overdue ? '1' : '',
    lauf: run,
    verein: club,
    veranstaltung: project,
  }
  function applyFilters(v: Partial<typeof filterParams>) {
    const next = new URLSearchParams()
    for (const [k, value] of Object.entries(v)) if (value) next.set(k, value)
    if (detail.value) next.set('rechnung', detail.value)
    setParams(next)
    setSearch(v.suche ?? '')
  }

  if (settings.error) return <Alert kind="error">{settings.error}</Alert>
  if (!settings.data) return <Loading />
  const s = settings.data
  // Empfänger der einfachen Rechnung: Mitglieder (Modul an) oder Untereinheiten
  const subUnitCount = (s.units ?? (s.org_type === 'federation' ? s.clubs : []))?.length ?? 0
  const hasRecipients =
    s.org_type === 'unit' ||
    ((s.keeps_members ?? s.org_type !== 'federation') && hasMembersModule(org)) ||
    subUnitCount > 0
  const statusLabels: Record<string, string> = {
    draft: t('Entwürfe'),
    open: t('offen'),
    paid: t('bezahlt'),
    settled: t('Abgerechnet'),
    cancelled: t('storniert'),
  }
  const chips: ActiveFilter[] = []
  if (term)
    chips.push({
      key: 'suche',
      label: `${t('Suche')}: ${term}`,
      onRemove: () => applyFilters({ ...filterParams, suche: '' }),
    })
  if (overdue || status)
    chips.push({
      key: 'status',
      label: `${t('Status')}: ${overdue ? t('überfällig') : (statusLabels[status] ?? status)}`,
      onRemove: () => applyFilters({ ...filterParams, status: '', ueberfaellig: '' }),
    })
  if (club)
    chips.push({
      key: 'verein',
      label: `${tm.Sg}: ${s.clubs.find((c) => String(c.id) === club)?.name ?? '…'}`,
      onRemove: () => applyFilters({ ...filterParams, verein: '' }),
    })
  if (run)
    chips.push({
      key: 'lauf',
      label: `${t('Beitragslauf')} ${runs.data?.find((r) => String(r.id) === run)?.label ?? '…'}`,
      onRemove: () => applyFilters({ ...filterParams, lauf: '' }),
    })
  if (project)
    chips.push({
      key: 'veranstaltung',
      label: t('Veranstaltung'),
      onRemove: () => applyFilters({ ...filterParams, veranstaltung: '' }),
    })
  const refresh = () => setVersion((v) => v + 1)

  return (
    <div className="stack">
      <div className="card card-wide filters">
        <form
          className="button-row"
          onSubmit={(e) => {
            e.preventDefault()
            setParam('suche', search.trim())
          }}
        >
          <input
            type="search"
            aria-label={t('Rechnungen durchsuchen')}
            placeholder={t('Name, Betreff oder Rechnungsnummer')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="button button-ghost">
            {t('Suchen')}
          </button>
        </form>
        <select
          aria-label={t('Status')}
          value={overdue ? 'ueberfaellig' : status}
          onChange={(e) => {
            const next = new URLSearchParams(params)
            next.delete('status')
            next.delete('ueberfaellig')
            next.delete('seite')
            if (e.target.value === 'ueberfaellig') next.set('ueberfaellig', '1')
            else if (e.target.value) next.set('status', e.target.value)
            setParams(next)
          }}
        >
          <option value="">{t('alle Status')}</option>
          <option value="draft">{t('Entwürfe')}</option>
          <option value="open">{t('offen')}</option>
          <option value="ueberfaellig">{t('überfällig')}</option>
          <option value="paid">{t('bezahlt')}</option>
          <option value="settled">{t('Abgerechnet')}</option>
          <option value="cancelled">{t('storniert')}</option>
        </select>
        {s.org_type === 'federation' && (
          <select
            aria-label={tm.Sg}
            value={params.get('verein') ?? ''}
            onChange={(e) => setParam('verein', e.target.value)}
          >
            <option value="">
              {t('alle')} {tm.pl}
            </option>
            {s.clubs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
        {org.type !== 'unit' && (
          <select
            aria-label={t('Beitragslauf')}
            value={run}
            onChange={(e) => setParam('lauf', e.target.value)}
          >
            <option value="">{t('alle Rechnungen')}</option>
            {(runs.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {t('Beitragslauf')} {r.label}
              </option>
            ))}
          </select>
        )}
        {runs.error && (
          <button type="button" className="link-button" onClick={() => void runs.reload()}>
            {t('Beitragsläufe nicht geladen, erneut laden')}
          </button>
        )}
        {s.can_edit && !creating && hasRecipients && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => detail.open('neu')}
          >
            {t('Neue Rechnung')}
          </button>
        )}
        {/* Ohne Mitglieder und Untereinheiten gehen Rechnungen an Geschäftspartner */}
        {s.can_edit && !creating && !hasRecipients && (
          <Link
            className="button button-ghost push-right"
            to="/finanzen/rechnungen/leistungen?rechnung=neu"
          >
            {t('Rechnung an Geschäftspartner')}
          </Link>
        )}
      </div>

      <div className="list-tools">
        <FilterChips filters={chips} onClearAll={() => applyFilters({})} />
        <ViewPicker
          list={`rechnungen.${org.id}`}
          current={filterParams}
          standard={{}}
          onApply={applyFilters}
        />
      </div>

      {creating && (
        <InvoiceForm
          settings={s}
          invoice={null}
          onCancel={detail.close}
          onSaved={(inv) => {
            detail.replace(String(inv.id))
            refresh()
          }}
        />
      )}

      {openId !== null && (
        <InvoiceDetail
          key={openId}
          id={openId}
          settings={s}
          onClose={detail.close}
          onChanged={refresh}
          onOpen={(other) => {
            detail.replace(String(other))
            refresh()
          }}
          onDeleted={() => {
            detail.close()
            refresh()
          }}
        />
      )}

      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!data && !error && (
        <p className="muted" role="status">
          {t('Wird geladen …')}
        </p>
      )}
      {data && (
        <div className="card card-wide">
          {data.results.length === 0 ? (
            <p className="muted">{t('Keine Rechnungen gefunden.')}</p>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Nummer')}</th>
                    <th>{t('Empfänger')}</th>
                    <th>{t('Datum')}</th>
                    <th>{t('Status')}</th>
                    <th className="num">{t('Betrag')}</th>
                    <th className="num">
                      <Term k="outstanding">{t('offen')}</Term>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => (
                    <tr key={r.id} className={r.id === openId ? 'row-active' : undefined}>
                      <td>
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => detail.open(String(r.id))}
                        >
                          {r.number}
                        </button>
                      </td>
                      <td>
                        {r.recipient_name.split('\n')[0]}
                        <div className="muted small">
                          {r.subject}
                          {r.sent_at && t(' · per E-Mail verschickt')}
                          {r.dunning_level > 0 &&
                            t(' · {dunning_level}. Mahnstufe', { dunning_level: r.dunning_level })}
                        </div>
                      </td>
                      <td>{formatDate(r.date)}</td>
                      <td>
                        <StatusBadge row={r} />
                      </td>
                      <td className="num">{euro(r.total)}</td>
                      <td className="num">{Number(r.outstanding) ? euro(r.outstanding) : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(data.next || data.previous) && (
            <PageNav
              prevDisabled={!data.previous}
              nextDisabled={!data.next}
              onPrev={() => setParams({ ...Object.fromEntries(params), seite: String(page - 1) })}
              onNext={() => setParams({ ...Object.fromEntries(params), seite: String(page + 1) })}
            >
              {t('Seite {page} · {count} Rechnungen', { page, count: data.count })}
            </PageNav>
          )}
        </div>
      )}
    </div>
  )
}
