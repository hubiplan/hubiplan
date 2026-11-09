// Finanzen › Steuern › Mittelverwendung: vereinfachte Mittelverwendungsrechnung
// (zeitnahe Mittelverwendung, § 55 Abs. 1 Nr. 5 AO; Konzept vereinskasse-steuern, S5).
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import { useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function UseOfFundsPage() {
  const org = useActiveOrg()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  const [year, setYear] = useState<number | null>(null)
  const current = year ?? settings.data?.current_year ?? null
  const report = useLoad(
    () => (current === null ? Promise.resolve(null) : financeApi.useOfFunds(org.id, current)),
    [org.id, current],
  )
  const loadError = settings.error ?? report.error
  if (loadError) return <Alert kind="error">{loadError}</Alert>
  if (!settings.data || !report.data) return <Loading />
  const d = report.data

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Mittelverwendung')}</h2>
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
      </div>
      <p className="muted small">
        {t(
          'Gemeinnützige Mittel müssen bis zum Ende des zweiten Geschäftsjahres nach dem Zufluss für die Satzungszwecke verwendet oder in zulässige Rücklagen eingestellt sein. Die Rechnung verwendet zuerst die ältesten Mittel. Grundlage sind die steuerlichen Bereiche der Kategorien; ein Anhaltspunkt, keine Steuerberatung.',
        )}
      </p>
      {Number(d.overdue) > 0 && (
        <Alert kind="error">
          {t(
            '{x} aus früheren Jahren sind nach dieser Rechnung nicht fristgerecht verwendet. Bitte mit der Steuerberatung klären, etwa durch Verwendung oder eine Rücklage.',
            { x: euro(d.overdue) },
          )}
        </Alert>
      )}
      {Number(d.due_now) > 0 && (
        <Alert kind="info">
          {t('{x} müssen bis zum Ende von {y} verwendet werden.', {
            x: euro(d.due_now),
            y: d.label,
          })}
        </Alert>
      )}
      <div className="card card-wide" data-testid="use-of-funds">
        <table className="table">
          <thead>
            <tr>
              <th />
              {d.years.map((y) => (
                <th key={y.year} className="num">
                  {y.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{t('Vortrag aus dem Vorjahr')}</td>
              {d.years.map((y) => (
                <td key={y.year} className="num">
                  {euro(y.carry_in)}
                </td>
              ))}
            </tr>
            <tr>
              <td>{t('zugeflossene Mittel')}</td>
              {d.years.map((y) => (
                <td key={y.year} className="num">
                  {euro(y.inflow)}
                </td>
              ))}
            </tr>
            <tr>
              <td>{t('aus Rücklagen aufgelöst')}</td>
              {d.years.map((y) => (
                <td key={y.year} className="num">
                  {euro(y.reserve_release)}
                </td>
              ))}
            </tr>
            <tr>
              <td>{t('für die Satzungszwecke verwendet')}</td>
              {d.years.map((y) => (
                <td key={y.year} className="num">
                  −{euro(y.used)}
                </td>
              ))}
            </tr>
            <tr>
              <td>{t('in Rücklagen eingestellt')}</td>
              {d.years.map((y) => (
                <td key={y.year} className="num">
                  −{euro(y.reserve_add)}
                </td>
              ))}
            </tr>
            <tr>
              <th>{t('noch zu verwenden')}</th>
              {d.years.map((y) => (
                <th key={y.year} className="num">
                  {euro(y.carry_out)}
                </th>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <div className="card card-wide">
        <h3>{t('Noch zu verwenden nach Herkunft')}</h3>
        {d.by_origin.length === 0 ? (
          <p className="muted">{t('Alle Mittel sind verwendet.')}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('zugeflossen in')}</th>
                <th>{t('zu verwenden bis Ende')}</th>
                <th className="num">{t('Betrag')}</th>
              </tr>
            </thead>
            <tbody>
              {d.by_origin.map((o) => (
                <tr key={o.year}>
                  <td>{o.label}</td>
                  <td>
                    {o.deadline}
                    {o.overdue && (
                      <>
                        {' '}
                        <span className="badge badge-open">{t('Frist abgelaufen')}</span>
                      </>
                    )}
                  </td>
                  <td className="num">{euro(o.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
