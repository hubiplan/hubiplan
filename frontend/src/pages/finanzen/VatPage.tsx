// Finanzen › Steuern › Umsatzsteuer: Vorlage für die Voranmeldung (Kennzahlen).
import { useState } from 'react'
import { euro, financeApi } from '../../api/finance.ts'
import type { FinanceSettings, VatPeriod } from '../../api/finance.ts'
import { formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

function periodOptions(): { value: VatPeriod; label: string }[] {
  return [
    { value: 'month', label: t('monatlich') },
    { value: 'quarter', label: t('vierteljährlich') },
    { value: 'year', label: t('jährlich') },
  ]
}

/** Erster Zeitraum, der schon abgelaufen ist oder läuft: der aktuelle */
function currentIndex(period: VatPeriod): number {
  const month = new Date().getMonth() + 1
  if (period === 'month') return month
  if (period === 'quarter') return Math.ceil(month / 3)
  return 1
}

export function VatPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  if (settings.error) return <Alert kind="error">{settings.error}</Alert>
  if (!settings.data) return <p className="muted">{t('Lädt …')}</p>
  return <VatReportView canEdit={canEdit} s={settings.data} reloadSettings={settings.reload} />
}

function VatReportView({
  canEdit,
  s,
  reloadSettings,
}: {
  canEdit: boolean
  s: FinanceSettings
  reloadSettings: () => void
}) {
  const org = useActiveOrg()
  const [thisYear] = useState(() => new Date().getFullYear())
  const [year, setYear] = useState(thisYear)
  const period: VatPeriod = s.vat_period ?? 'quarter'
  const [index, setIndex] = useState<number | null>(null)
  const shown = index ?? currentIndex(period)
  const report = useLoad(
    () => financeApi.vat(org.id, year, period, shown),
    [org.id, year, period, shown],
  )
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  async function change(data: Partial<FinanceSettings>) {
    setSaving(true)
    setFailure(null)
    try {
      await financeApi.updateSettings(org.id, data)
      if (data.vat_period) setIndex(null)
      reloadSettings()
      report.reload()
    } catch (err) {
      setFailure(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  if (report.error) return <Alert kind="error">{report.error}</Alert>
  if (!report.data) return <p className="muted">{t('Lädt …')}</p>
  const data = report.data
  const editable = canEdit && s.can_edit

  return (
    <div className="stack" data-testid="vat">
      <h2 className="section-heading">{t('Umsatzsteuer-Voranmeldung')}</h2>
      <p className="muted small">
        {t(
          'Vorlage zum Übertragen in ELSTER. Gezählt werden Buchungen mit Steuersatz; der Betrag im Kassenbuch ist brutto. Vorsteuer zählt nur bei Ausgaben außerhalb des ideellen Bereichs.',
        )}
      </p>
      <div className="card card-wide filters">
        <label>
          {t('Jahr')}{' '}
          <select
            value={year}
            onChange={(e) => {
              setYear(Number(e.target.value))
              setIndex(null)
            }}
          >
            {[0, 1, 2, 3].map((i) => (
              <option key={i} value={thisYear - i}>
                {thisYear - i}
              </option>
            ))}
          </select>
        </label>
        {data.periods.length > 1 && (
          <label>
            {t('Zeitraum')}{' '}
            <select value={shown} onChange={(e) => setIndex(Number(e.target.value))}>
              {data.periods.map((p) => (
                <option key={p.index} value={p.index}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="muted small">
          {formatDate(data.start)} – {formatDate(data.end)}
        </span>
      </div>

      {data.counted_at && (
        <Alert kind="info">
          {t('Diese Kasse zählt steuerlich bei {x} mit.', { x: data.counted_at })}
        </Alert>
      )}
      {data.units.length > 0 && (
        <p className="muted small">
          {t('Mitgezählt werden die Kassen von: {units}', { units: data.units.join(', ') })}
        </p>
      )}
      {data.warnings.map((w) => (
        <Alert key={w.kind} kind={w.kind === 'small' ? 'info' : 'error'}>
          {w.text}
        </Alert>
      ))}

      <div className="card card-wide">
        <table className="table">
          <thead>
            <tr>
              <th>{t('Kennzahl')}</th>
              <th>{t('Bezeichnung')}</th>
              <th className="num">{t('Bemessungsgrundlage')}</th>
              <th className="num">{t('Steuer')}</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((line) => (
              <tr key={line.code}>
                <td>{line.code === '83' ? <strong>{line.code}</strong> : line.code}</td>
                <td>{line.label}</td>
                <td className="num">
                  {line.base === null ? (
                    ''
                  ) : (
                    <>
                      {euro(line.base)}
                      <div className="muted small">
                        {t('einzutragen: {x} €', { x: line.base_euros ?? 0 })}
                      </div>
                    </>
                  )}
                </td>
                <td className="num">{line.tax === null ? '' : euro(line.tax)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          {t('Tatsächliche Vorsteuer {a}, Pauschale nach § 23a UStG {b}.', {
            a: euro(data.actual_input_tax),
            b: euro(data.flat_input_tax),
          })}
        </p>
      </div>

      <div className="card card-wide stack">
        <h3>{t('Einstellungen')}</h3>
        <Checkbox
          label={t('Der Verein ist umsatzsteuerpflichtig (kein Kleinunternehmer)')}
          hint={t(
            'Dieselbe Angabe wie „Umsatzsteuer auf Rechnungen ausweisen“ bei den Rechnungen.',
          )}
          checked={!!s.vat_registered}
          disabled={!editable || saving}
          onChange={(on) => change({ vat_registered: on })}
        />
        <SelectField
          label={t('Voranmeldungszeitraum')}
          value={period}
          disabled={!editable || saving}
          onChange={(e) => change({ vat_period: e.target.value as VatPeriod })}
        >
          {periodOptions().map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </SelectField>
        <Checkbox
          label={t('Vorsteuer pauschal nach § 23a UStG (7 % der steuerpflichtigen Umsätze)')}
          hint={t(
            'Nur wenn die steuerpflichtigen Umsätze im Vorjahr 50.000 € nicht überstiegen haben (Vorjahr: {x}). Die Wahl bindet fünf Kalenderjahre.',
            { x: euro(data.previous_taxable) },
          )}
          checked={!!s.vat_flat_rate}
          disabled={!editable || saving}
          onChange={(on) => change({ vat_flat_rate: on })}
        />
        {failure && <Alert kind="error">{failure}</Alert>}
      </div>
    </div>
  )
}
