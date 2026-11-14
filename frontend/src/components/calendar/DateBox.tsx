// Datumskästchen vor Terminen (Design „Frisch“ D5): Tag groß, Monat klein. Rein schmückend;
// das ausgeschriebene Datum steht daneben und wird vorgelesen.
import { locale } from '../../i18n/index.ts'

export function DateBox({ date }: { date: string }) {
  const [y, m, d] = date.split('-').map(Number)
  const month = new Intl.DateTimeFormat(locale(), { month: 'short', timeZone: 'UTC' })
    .format(new Date(Date.UTC(y, m - 1, d)))
    .replace('.', '')
  return (
    <span className="date-box" aria-hidden="true">
      <b>{String(d).padStart(2, '0')}</b>
      <span>{month}</span>
    </span>
  )
}
