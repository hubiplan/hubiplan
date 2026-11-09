// Finanzen › Steuern › Künstlersozialabgabe: Honorare an selbständige Künstler
// je Kalenderjahr als Vorlage für die Meldung an die Künstlersozialkasse.
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { locale, t } from '../../i18n/index.ts'

export function ArtistFeesPage() {
  const org = useActiveOrg()
  // Gemeldet wird bis Ende März für das Vorjahr: bis dahin das Vorjahr zeigen
  const [now] = useState(() => new Date())
  const thisYear = now.getFullYear()
  const [year, setYear] = useState(now.getMonth() < 3 ? thisYear - 1 : thisYear)
  const report = useLoad(() => financeApi.artistFees(org.id, year), [org.id, year])
  if (report.error) return <Alert kind="error">{report.error}</Alert>
  if (!report.data) return <Loading />
  const data = report.data

  return (
    <div className="stack">
      <h2 className="section-heading">
        <Term k="artist_levy">{t('Künstlersozialabgabe')}</Term>
      </h2>
      <Why k="artist_fee_mark" />
      <div className="card card-wide filters">
        <label>
          {t('Kalenderjahr')}{' '}
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[0, 1, 2, 3, 4].map((i) => (
              <option key={i} value={thisYear - i}>
                {thisYear - i}
              </option>
            ))}
          </select>
        </label>
        <span className="push-right">
          <a className="button button-ghost" href={financeApi.artistFeesXlsxUrl(org.id, data.year)}>
            {t('Excel')}
          </a>
        </span>
      </div>
      <p className="muted small">
        {t(
          'Gezählt werden Ausgaben, die im Kassenbuch als Honorar an Künstler gekennzeichnet sind oder deren Kategorie so markiert ist (Einrichtung › Kategorien), etwa für Kapelle, Tambourcorps, DJ oder Grafiker. Gemeldet werden die Honorare ohne gesondert ausgewiesene Umsatzsteuer.',
        )}
      </p>
      <div className="card card-wide" data-testid="artist-fees-total">
        <table className="table">
          <tbody>
            <tr>
              <th>{t('Honorare {y}', { y: data.year })}</th>
              <td className="num">{euro(data.total)}</td>
            </tr>
            <tr>
              <th>{t('Abgabe ({p} %)', { p: Number(data.rate).toLocaleString(locale()) })}</th>
              <td className="num">{euro(data.levy)}</td>
            </tr>
          </tbody>
        </table>
        <p className="small">
          {t('Meldung an die Künstlersozialkasse bis {d}.', { d: formatDate(data.due) })}{' '}
          {data.over_threshold
            ? t(
                'Die Summe liegt über {x}. Ist der Verein bei der Künstlersozialkasse noch nicht erfasst, bitte die Abgabepflicht prüfen.',
                { x: euro(data.threshold) },
              )
            : t(
                'Bei Veranstaltungen und Eigenwerbung bleibt eine Summe bis {x} im Jahr abgabefrei.',
                { x: euro(data.threshold) },
              )}
        </p>
      </div>
      <div className="card card-wide">
        <h3>{t('Je Empfänger')}</h3>
        {data.recipients.length === 0 ? (
          <p className="muted">
            {t(
              'Noch keine Künstlerhonorare in {y}. Im Kassenbuch bei einer Ausgabe „Honorar an Künstler“ anhaken oder die Kategorie markieren.',
              { y: data.year },
            )}
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Empfänger')}</th>
                <th className="num">{t('Buchungen')}</th>
                <th className="num">{t('Summe')}</th>
              </tr>
            </thead>
            <tbody>
              {data.recipients.map((r) => (
                <tr key={r.name}>
                  <td>{r.name || t('ohne Empfänger')}</td>
                  <td className="num">{r.count}</td>
                  <td className="num">{euro(r.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
