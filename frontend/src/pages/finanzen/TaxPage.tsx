// Finanzen › Steuern: Freigrenze, Bereiche, Kleinunternehmer.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { euro, financeApi } from '../../api/finance.ts'
import type { TaxArea, TaxReport, TaxStatus } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import type { TermKey } from '../../learning/content.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

const AREA_TERMS: Record<string, TermKey> = {
  ideal: 'ideal_area',
  assets: 'asset_management',
  purpose: 'purpose_operation',
  business: 'commercial_operation',
}

const ALERT: Record<TaxStatus, 'info' | 'error'> = {
  ok: 'info',
  warn: 'info',
  over: 'error',
}

function statusText(status: TaxStatus): string {
  if (status === 'over') return t('überschritten')
  if (status === 'warn') return t('nahe an der Grenze')
  return t('unter der Grenze')
}

/** Ampel zur Freigrenze des wirtschaftlichen Geschäftsbetriebs (auch für die Übersicht). */
export function FreeLimitMeter({ report }: { report: TaxReport }) {
  const fl = report.free_limit
  return (
    <div data-testid="tax-free-limit">
      <p>
        <Term k="commercial_operation">{t('Einnahmen wirtschaftlicher Geschäftsbetrieb')}</Term>{' '}
        {report.label}:{' '}
        <strong>{t('{x} von {y}', { x: euro(fl.income), y: euro(fl.limit) })}</strong> ({fl.percent}{' '}
        %, {statusText(fl.status)})
      </p>
      <meter
        className={`tax-meter tax-meter-${fl.status}`}
        min={0}
        max={Number(fl.limit)}
        low={Number(fl.limit) * 0.8}
        high={Number(fl.limit)}
        optimum={0}
        value={Math.min(Number(fl.income), Number(fl.limit))}
        aria-label={t('Anteil an der Freigrenze')}
      />
    </div>
  )
}

/** Kurzfassung für die Finanzübersicht: nur, wenn etwas zu beachten ist. */
export function TaxSignal({ orgId, year }: { orgId: number; year: number }) {
  const { data } = useLoad(() => financeApi.taxReport(orgId, year), [orgId, year])
  if (!data || !data.enabled) return null
  const attention =
    data.free_limit.status !== 'ok' ||
    (data.small_business !== null && data.small_business.status !== 'ok') ||
    data.warnings.some((w) => w.kind === 'loss') ||
    !!data.declaration?.due
  if (!attention) return null
  return (
    <Alert kind={data.free_limit.status === 'over' ? 'error' : 'info'}>
      {t('In der steuerlichen Auswertung gibt es Hinweise.')}{' '}
      <Link to="/finanzen/steuern">{t('Ansehen')}</Link>
    </Alert>
  )
}

function AreaTable({ areas }: { areas: TaxArea[] }) {
  if (areas.length === 0) return <p className="muted">{t('Keine Einnahmen oder Ausgaben.')}</p>
  return (
    <table className="table">
      <thead>
        <tr>
          <th>{t('Bereich')}</th>
          <th className="num">{t('Einnahmen')}</th>
          <th className="num">{t('Ausgaben')}</th>
          <th className="num">{t('Ergebnis')}</th>
        </tr>
      </thead>
      <tbody>
        {areas.map((a) => (
          <tr key={a.area || 'ohne'}>
            <td>
              {a.area && AREA_TERMS[a.area] ? (
                <Term k={AREA_TERMS[a.area]}>{a.label}</Term>
              ) : (
                a.label
              )}
            </td>
            <td className="num">{euro(a.income)}</td>
            <td className="num">{euro(a.expense)}</td>
            <td className="num">{euro(a.result)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ownIncome(report: TaxReport, area: string): number {
  return Number(report.own_areas.find((a) => a.area === area)?.income ?? 0)
}

export function TaxPage() {
  const org = useActiveOrg()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  const [year, setYear] = useState<number | null>(null)
  const current = year ?? settings.data?.current_year ?? null
  const report = useLoad(
    () => (current === null ? Promise.resolve(null) : financeApi.taxReport(org.id, current)),
    [org.id, current],
  )
  const error = settings.error ?? report.error
  if (error) return <Alert kind="error">{error}</Alert>
  if (!settings.data || !report.data) return <Loading />
  const data = report.data
  if (!data.enabled)
    return (
      <div className="card card-wide">
        <h2>{t('Steuerliche Auswertung')}</h2>
        <p>
          {t(
            'Dafür müssen die Kategorien steuerlichen Bereichen zugeordnet sein. Einschalten unter Einrichtung › Kategorien.',
          )}
        </p>
        <Link className="button" to="/finanzen/einrichtung/kategorien">
          {t('Zu den Kategorien')}
        </Link>
      </div>
    )
  const fl = data.free_limit
  const sb = data.small_business
  return (
    <div className="stack">
      <h2 className="section-heading">{t('Steuerliche Auswertung')}</h2>
      <div className="card card-wide filters">
        <label>
          {t('Geschäftsjahr')}{' '}
          <select value={data.year} onChange={(e) => setYear(Number(e.target.value))}>
            {settings.data.years.map((y) => (
              <option key={y.year} value={y.year}>
                {y.label}
              </option>
            ))}
          </select>
        </label>
        <span className="muted small">
          {t('{a} bis {b} · Veranlagungszeitraum {p}', {
            a: formatDate(data.start_date),
            b: formatDate(data.end_date),
            p: data.period,
          })}
        </span>
        <span className="button-row push-right">
          <a
            className="button button-ghost"
            href={financeApi.taxReportUrl(org.id, data.year, 'pdf')}
            target="_blank"
            rel="noreferrer"
          >
            {t('PDF')}
          </a>
          <a
            className="button button-ghost"
            href={financeApi.taxReportUrl(org.id, data.year, 'xlsx')}
          >
            {t('Excel')}
          </a>
        </span>
      </div>
      <p className="muted small">
        {t(
          'Stornos sind mit der stornierten Buchung verrechnet. Die Auswertung ist eine Vorlage für Steuererklärung und Beratung, keine Steuerberatung.',
        )}
      </p>

      {!data.root.is_self && (
        <Alert kind="info">
          {t(
            'Diese Kasse zählt steuerlich bei {name} mit. Freigrenze und Kleinunternehmergrenze gelten für die Summe dort; hier stehen nur die eigenen Zahlen.',
            { name: data.root.name },
          )}
        </Alert>
      )}

      <div className="card card-wide">
        <h2>{t('Freigrenze')}</h2>
        <FreeLimitMeter report={data} />
        <p className="muted small">
          {t(
            'Bis zu dieser Grenze fallen auf den wirtschaftlichen Geschäftsbetrieb keine Körperschaft- und Gewerbesteuer an (§ 64 Abs. 3 AO). Gezählt werden die Einnahmen einschließlich Umsatzsteuer.',
          )}
        </p>
        {fl.status === 'over' && (
          <Alert kind="error">
            {t(
              'Die Freigrenze ist überschritten. Der Gewinn des wirtschaftlichen Geschäftsbetriebs ist steuerpflichtig (Freibetrag 5.000 €). Bitte mit der Steuerberatung klären.',
            )}
          </Alert>
        )}
        <table className="table">
          <thead>
            <tr>
              <th>{t('Geschäftsjahr')}</th>
              <th className="num">{t('Einnahmen')}</th>
              <th className="num">{t('Ergebnis')}</th>
            </tr>
          </thead>
          <tbody>
            {data.history.map((h) => (
              <tr key={h.year}>
                <td>{h.label}</td>
                <td className="num">{euro(h.income)}</td>
                <td className="num">{euro(h.result)}</td>
              </tr>
            ))}
            <tr>
              <th>{data.label}</th>
              <th className="num">{euro(fl.income)}</th>
              <th className="num">{euro(data.business_result)}</th>
            </tr>
          </tbody>
        </table>
      </div>

      {data.depreciation && (
        <div className="card card-wide" data-testid="tax-depreciation">
          <h2>{t('Abschreibung')}</h2>
          <p className="muted small">
            {t(
              'Für das Ergebnis zählt bei Anlagen nicht die Ausgabe der Anschaffung, sondern die Abschreibung über die Nutzungsdauer. Das Kassenbuch bleibt unverändert.',
            )}
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>{t('Bereich')}</th>
                <th className="num">{t('Anschaffungen')}</th>
                <th className="num">{t('Abschreibung')}</th>
                <th className="num">{t('Restwert Abgang')}</th>
                <th className="num">{t('Korrektur')}</th>
              </tr>
            </thead>
            <tbody>
              {data.depreciation.areas.map((a) => (
                <tr key={a.area}>
                  <td>{a.label}</td>
                  <td className="num">{euro(a.purchases)}</td>
                  <td className="num">{euro(a.depreciation)}</td>
                  <td className="num">{euro(a.residual)}</td>
                  <td className="num">{euro(a.adjustment)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.business_result_after !== null && (
            <p>
              {t('Ergebnis wirtschaftlicher Geschäftsbetrieb nach Abschreibung: {x}', {
                x: euro(data.business_result_after),
              })}
            </p>
          )}
          <Link to="/finanzen/anlagen">{t('Zum Anlagenverzeichnis')}</Link>
        </div>
      )}

      {data.warnings.map((w) => (
        <Alert key={w.kind} kind={w.kind === 'loss' ? 'error' : 'info'}>
          {w.text}
        </Alert>
      ))}

      <div className="card card-wide">
        <h2>{t('Nach steuerlichem Bereich')}</h2>
        <AreaTable areas={data.areas} />
        {data.units.length > 0 && (
          <>
            <h3>{t('Enthaltene Kassen')}</h3>
            <p className="muted small">
              {t(
                'Untereinheiten mit eigener Kasse zählen hier mit, solange sie nicht als steuerlich selbständig markiert sind.',
              )}
            </p>
            <Why k="unit_tax_independent" />
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Kasse')}</th>
                  <th className="num">{t('Einnahmen wGB')}</th>
                  <th className="num">{t('Umsatz')}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{org.name}</td>
                  <td className="num">{euro(ownIncome(data, 'business'))}</td>
                  <td className="num">
                    {euro(ownIncome(data, 'business') + ownIncome(data, 'purpose'))}
                  </td>
                </tr>
                {data.units.map((u) => (
                  <tr key={u.id}>
                    <td>
                      {u.name}
                      {!u.tax_areas_enabled && (
                        <div className="muted small">
                          {t('ohne steuerliche Bereiche: zählt nicht in der Ampel')}
                        </div>
                      )}
                    </td>
                    <td className="num">{euro(u.business_income)}</td>
                    <td className="num">{euro(u.turnover)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      {sb && (
        <div className="card card-wide">
          <h2>
            <Term k="small_business">{t('Kleinunternehmergrenze')}</Term>
          </h2>
          <Alert kind={ALERT[sb.status]}>
            {t(
              'Umsatz aus Zweckbetrieb und wirtschaftlichem Geschäftsbetrieb: Vorjahr {a} (Grenze {b}), laufendes Jahr {c} (Grenze {d}), {s}.',
              {
                a: euro(sb.previous),
                b: euro(sb.previous_limit),
                c: euro(sb.current),
                d: euro(sb.current_limit),
                s: statusText(sb.status),
              },
            )}
          </Alert>
          <p className="muted small">
            {t(
              'Anhaltspunkt: Die Grenzen gelten netto (§ 19 UStG). Steuerfreie Umsätze und Vermietung prüft am besten die Steuerberatung. Weist die Einheit auf Rechnungen Umsatzsteuer aus, entfällt diese Prüfung.',
            )}
          </p>
        </div>
      )}

      {data.declaration && (
        <div className="card card-wide">
          <h2>{t('Steuererklärung')}</h2>
          <Alert kind={data.declaration.due ? 'error' : 'info'}>{data.declaration.text}</Alert>
          <Link to="/finanzen/einrichtung/zuwendungen">{t('Angaben zum Bescheid')}</Link>
        </div>
      )}
    </div>
  )
}
