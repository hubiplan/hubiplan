// Stand des Schießnachweises nach § 14 WaffG (Verwaltung und Mitgliederbereich).
import type { Evaluation, Span } from '../../api/training.ts'
import { formatDate } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

function Mark({ ok }: { ok: boolean }) {
  return (
    <span className={ok ? 'status status-paid' : 'status status-overdue'}>
      {ok ? t('erfüllt') : t('nicht erfüllt')}
    </span>
  )
}

function Spans({ items, label }: { items: Span[]; label: string }) {
  return (
    <ol className="training-spans" aria-label={label}>
      {items.map((s) => (
        <li
          key={s.start}
          className={s.count ? 'training-span training-span-ok' : 'training-span'}
          title={`${formatDate(s.start)} – ${formatDate(s.end)}: ${s.count}`}
        >
          <span className="sr-only">
            {t('{start} bis {end}: {n} Termine', {
              start: formatDate(s.start),
              end: formatDate(s.end),
              n: s.count,
            })}
          </span>
          <span aria-hidden="true">{s.count}</span>
        </li>
      ))}
    </ol>
  )
}

export function EvaluationCard({ evaluation }: { evaluation: Evaluation }) {
  const acq = evaluation.acquisition
  return (
    <section className="card stack training-eval">
      <h2>{t('Schießnachweis nach § 14 WaffG')}</h2>
      <p className="muted small">
        {t(
          'Stand {date}. Es zählen nur vom Verein bestätigte Termine mit erlaubnispflichtigen Waffen, je Tag höchstens einer je Disziplin. Was der Verband anerkennt, entscheidet er selbst.',
          { date: formatDate(evaluation.on) },
        )}
      </p>
      <h3>
        {t('Erwerb (Abs. 3): letzte 12 Monate')} <Mark ok={acq.ok} />
      </h3>
      <ul className="plain-list">
        <li>
          {acq.member_12_months
            ? t('Seit mindestens zwölf Monaten Mitglied (seit {date}).', {
                date: formatDate(evaluation.member_since),
              })
            : t('Noch keine zwölf Monate Mitglied.')}
        </li>
        <li>
          {t('In jedem Monat geschossen: {state}.', {
            state: acq.by_months ? t('ja') : t('nein'),
          })}
        </li>
        <li>{t('Termine insgesamt: {n} von {needed}.', { n: acq.count, needed: acq.needed })}</li>
        {!acq.gap_ok && (
          <li className="training-hint">
            {t(
              'Längere Pause: {days} Tage ohne Schießtermin. Der BSSB erlaubt höchstens vier Monate ohne Begründung.',
              { days: acq.longest_gap_days },
            )}
          </li>
        )}
        {!acq.mostly_own_club && (
          <li className="training-hint">
            {t(
              'Mehr Termine in anderen Vereinen ({external}) als im eigenen ({internal}). Verbände erwarten meist die Mehrheit im eigenen Verein.',
              { external: acq.external, internal: acq.internal },
            )}
          </li>
        )}
      </ul>
      <Spans items={acq.months} label={t('Termine je Monat')} />
      {evaluation.possession.map((p) => (
        <div key={p.weapon_class} className="stack-sm">
          <h3>
            {t('Besitz (Abs. 4), {label}: letzte 24 Monate', { label: p.label })} <Mark ok={p.ok} />
          </h3>
          <p className="small">
            {t('Jedes Quartal: {q}. Sechsmal je zwölf Monate: {six} ({a} und {b}).', {
              q: p.by_quarters ? t('ja') : t('nein'),
              six: p.by_six ? t('ja') : t('nein'),
              a: p.years[0]?.count ?? 0,
              b: p.years[1]?.count ?? 0,
            })}
          </p>
          <Spans items={p.quarters} label={t('Termine je Quartal')} />
        </div>
      ))}
      <p className="muted small">
        {t(
          'Nach zehn Jahren seit der ersten Waffenbesitzkarte genügt für das Fortbestehen des Bedürfnisses die Mitgliedschaft.',
        )}
      </p>
      {evaluation.pending > 0 && (
        <p className="training-hint">
          {t('{n} gemeldete Termine warten auf die Bestätigung des Vereins.', {
            n: evaluation.pending,
          })}
        </p>
      )}
    </section>
  )
}
