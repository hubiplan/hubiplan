// Finanzen › Abschluss & Berichte › Vermögen: Vermögensübersicht zum Ende eines
// Geschäftsjahres (Kontenstände, Forderungen, Anlagen, Verbindlichkeiten, Rücklagen).
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function NetAssetsPage() {
  const org = useActiveOrg()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  const [year, setYear] = useState<number | null>(null)
  const current = year ?? settings.data?.current_year ?? null
  const report = useLoad(
    () => (current === null ? Promise.resolve(null) : financeApi.netAssets(org.id, current)),
    [org.id, current],
  )
  const loadError = settings.error ?? report.error
  if (loadError) return <Alert kind="error">{loadError}</Alert>
  if (!settings.data || !report.data) return <p className="muted">{t('Lädt …')}</p>
  const d = report.data

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Vermögensübersicht')}</h2>
      <div className="card card-wide filters">
        <label>
          {t('Geschäftsjahr')}{' '}
          <select value={d.year} onChange={(e) => setYear(Number(e.target.value))}>
            {settings.data.years.map((y) => (
              <option key={y.year} value={y.year}>
                {y.label}
              </option>
            ))}
          </select>
        </label>
        <span className="muted small">{t('Stand am {d}', { d: formatDate(d.end_date) })}</span>
      </div>
      <p className="muted small">
        {t(
          'Was der Verein am Ende des Geschäftsjahres besitzt und schuldet. Was erst danach bezahlt wurde, zählt hier noch als offen. Die Übersicht steht auch im Kassenbericht.',
        )}
      </p>
      <div className="card card-wide" data-testid="net-assets">
        <table className="table">
          <tbody>
            {d.accounts.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td>
                <td className="num">{euro(a.balance)}</td>
              </tr>
            ))}
            <tr>
              <th>{t('Kontenstände')}</th>
              <th className="num">{euro(d.cash)}</th>
            </tr>
            <tr>
              <td>
                {t('Offene Forderungen')}
                <div className="muted small">
                  {t('{n} Rechnungen, am Stichtag nicht bezahlt', { n: d.receivables.count })}
                </div>
              </td>
              <td className="num">{euro(d.receivables.total)}</td>
            </tr>
            {d.fixed_assets && (
              <tr>
                <td>
                  {t('Anlagevermögen (Buchwert)')}
                  <div className="muted small">
                    {t('{n} Anlagen laut Anlagenverzeichnis', { n: d.fixed_assets.count })}
                  </div>
                </td>
                <td className="num">{euro(d.fixed_assets.total)}</td>
              </tr>
            )}
            <tr>
              <td>
                {t('Offene Verbindlichkeiten')}
                <div className="muted small">
                  {t('{n} Eingangsrechnungen, am Stichtag nicht bezahlt', {
                    n: d.liabilities.count,
                  })}
                </div>
              </td>
              <td className="num">−{euro(d.liabilities.total)}</td>
            </tr>
            <tr>
              <th>{t('Vermögen')}</th>
              <th className="num">{euro(d.net)}</th>
            </tr>
            {d.reserves && (
              <>
                <tr>
                  <td>{t('davon in Rücklagen gebunden')}</td>
                  <td className="num">{euro(d.reserves.total)}</td>
                </tr>
                <tr>
                  <td>{t('frei verfügbar')}</td>
                  <td className="num">{euro(d.free)}</td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>
      {d.liabilities.items.length > 0 && (
        <div className="card card-wide">
          <h3>{t('Offene Eingangsrechnungen')}</h3>
          <table className="table">
            <thead>
              <tr>
                <th>{t('Rechnungssteller')}</th>
                <th>{t('Nummer')}</th>
                <th>{t('fällig am')}</th>
                <th className="num">{t('Betrag')}</th>
              </tr>
            </thead>
            <tbody>
              {d.liabilities.items.map((i) => (
                <tr key={`${i.seller}-${i.number}-${i.date}`}>
                  <td>{i.seller || '–'}</td>
                  <td>{i.number || '–'}</td>
                  <td>{formatDate(i.due_date)}</td>
                  <td className="num">{euro(i.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
