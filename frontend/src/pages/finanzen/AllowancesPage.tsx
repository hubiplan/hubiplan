// Finanzen › Buchen › Pauschalen: Übungsleiterfreibetrag und Ehrenamtspauschale.
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import type { TaxStatus } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'

function statusText(status: TaxStatus): string {
  if (status === 'over') return t('über dem Freibetrag')
  if (status === 'warn') return t('nahe am Freibetrag')
  return t('im Rahmen')
}

export function AllowancesPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [thisYear] = useState(() => new Date().getFullYear())
  const [year, setYear] = useState(thisYear)
  const [saving, setSaving] = useState(false)
  const report = useLoad(() => financeApi.allowances(org.id, year), [org.id, year])
  if (report.error) return <Alert kind="error">{report.error}</Alert>
  if (!report.data) return <Loading />
  const data = report.data

  async function toggleBoard(on: boolean) {
    setSaving(true)
    try {
      await financeApi.updateSettings(org.id, { board_pay_allowed: on })
      report.reload()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Aufwandsvergütungen')}</h2>
      <p className="muted small">
        <Term k="trainer_allowance">{t('Übungsleiterfreibetrag')}</Term>
        {' · '}
        <Term k="volunteer_allowance">{t('Ehrenamtspauschale')}</Term>
      </p>
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
        <span className="muted small">
          {t('Freibeträge {y}: Übungsleiter {a}, Ehrenamt {b} je Person', {
            y: data.year,
            a: euro(data.limits.trainer),
            b: euro(data.limits.volunteer),
          })}
        </span>
      </div>
      <p className="muted small">
        {t(
          'Gezählt werden Ausgaben, bei denen im Kassenbuch eine Aufwandsvergütung gewählt ist. Die Freibeträge gelten je Person und Kalenderjahr über alle Auftraggeber zusammen. Deshalb unterschreibt der Empfänger eine Erklärung, dass er sie nicht anderweitig nutzt.',
        )}{' '}
        {t(
          'Ein Verzicht auf die Pauschale als Aufwandsspende zählt ebenso, Auszahlungen aus der Musikerabrechnung zählen beim Musiker.',
        )}
      </p>
      {data.units.length > 0 && (
        <p className="muted small" data-testid="allowance-units">
          {t('Mitgezählt werden die Kassen von: {units}', { units: data.units.join(', ') })}
        </p>
      )}
      {data.counted_at && (
        <Alert kind="info">
          {t(
            'Diese Kasse zählt steuerlich bei {x} mit. Dort stehen die Summen je Person über alle Kassen.',
            { x: data.counted_at },
          )}
        </Alert>
      )}

      {data.warnings.map((w) => (
        <Alert key={w.kind} kind="error">
          {w.text}
        </Alert>
      ))}

      <div className="card card-wide">
        {data.people.length === 0 ? (
          <p className="muted">
            {t(
              'Noch keine Aufwandsvergütungen in {y}. Im Kassenbuch bei einer Ausgabe „Aufwandsvergütung an eine Person“ wählen.',
              { y: data.year },
            )}
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Person')}</th>
                <th>{t('Art')}</th>
                <th className="num">{t('Gezahlt')}</th>
                <th className="num">{t('Freibetrag')}</th>
                <th>{t('Stand')}</th>
                <th>{t('Erklärung')}</th>
              </tr>
            </thead>
            <tbody>
              {data.people.flatMap((p) =>
                p.kinds.map((k, i) => (
                  <tr key={`${p.key}-${k.kind}`}>
                    <td>
                      {i === 0 && (
                        <>
                          {p.name}
                          {p.board && <div className="muted small">{t('Vorstand')}</div>}
                          <details className="small">
                            <summary>{t('{n} Zahlungen', { n: p.bookings.length })}</summary>
                            <ul className="plain-list">
                              {p.bookings.map((b) => (
                                <li key={`${b.source}-${b.id}`}>
                                  {formatDate(b.date)} · {b.display_number} · {euro(b.amount)}
                                  {b.unit && ` · ${b.unit}`}
                                </li>
                              ))}
                            </ul>
                          </details>
                        </>
                      )}
                    </td>
                    <td>{k.label}</td>
                    <td className="num">{euro(k.total)}</td>
                    <td className="num">{euro(k.limit)}</td>
                    <td>
                      {k.status === 'over' ? '⚠ ' : ''}
                      {k.percent} %, {statusText(k.status)}
                    </td>
                    <td>
                      {i === 0 && (
                        <a
                          href={financeApi.allowanceDeclarationUrl(org.id, data.year, p.key)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {t('PDF')}
                        </a>
                      )}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="card card-wide">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={data.board_pay_allowed}
            disabled={!canEdit || saving}
            onChange={(e) => toggleBoard(e.target.checked)}
          />{' '}
          {t('Unsere Satzung erlaubt eine Vergütung des Vorstands')}
        </label>
        <Why k="board_pay" />
        <p className="muted small">
          {t(
            'Ohne Regelung in der Satzung ist der Vorstand unentgeltlich tätig (§ 27 Abs. 3 BGB). Dann warnt HUBIplan, wenn ein Vorstandsmitglied eine Pauschale erhält.',
          )}
        </p>
      </div>
    </div>
  )
}
