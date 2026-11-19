import { locale, t } from '../../i18n/index.ts'

/** Zeitangaben der Belegung (deutsche Zeit), auch für die Mitgliedsakte. */
export const ZONE = 'Europe/Berlin'

// Tag in deutscher Zeit als JJJJ-MM-TT
export function dayKey(value: Date | string) {
  return new Date(value).toLocaleDateString('sv-SE', { timeZone: ZONE })
}

export function noon(key: string) {
  return new Date(key + 'T12:00:00Z')
}

export function addDays(key: string, days: number) {
  const d = new Date(`${key}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function monday(key: string) {
  const d = new Date(`${key}T12:00:00Z`)
  return addDays(key, -((d.getUTCDay() + 6) % 7))
}

export function time(value: string) {
  return new Date(value).toLocaleTimeString(locale(), {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function statusLabel(status: string) {
  return (
    {
      requested: t('angefragt'),
      confirmed: t('bestätigt'),
      rejected: t('abgelehnt'),
      cancelled: t('storniert'),
    }[status] ?? status
  )
}

export function span(row: { starts_at: string; ends_at: string; all_day: boolean }) {
  if (row.all_day) {
    const last = addDays(dayKey(row.ends_at), -1)
    const first = dayKey(row.starts_at)
    const fmt = (k: string) =>
      new Date(`${k}T12:00:00Z`).toLocaleDateString(locale(), { timeZone: 'UTC' })
    return first === last ? `${fmt(first)} · ${t('ganztägig')}` : `${fmt(first)} – ${fmt(last)}`
  }
  const start = new Date(row.starts_at).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  })
  return dayKey(row.starts_at) === dayKey(row.ends_at)
    ? `${start} – ${time(row.ends_at)}`
    : `${start} – ${new Date(row.ends_at).toLocaleString(locale(), {
        timeZone: ZONE,
        dateStyle: 'short',
        timeStyle: 'short',
      })}`
}

export function monthStart(key: string) {
  return `${key.slice(0, 7)}-01`
}

export function addMonths(key: string, months: number) {
  const d = new Date(`${monthStart(key)}T12:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() + months)
  return d.toISOString().slice(0, 10)
}

/** Tage (JJJJ-MM-TT), die eine Belegung berührt; ganztägig ohne den Folgetag 0:00. */
export function daysOf(row: { starts_at: string; ends_at: string; all_day: boolean }) {
  const first = dayKey(row.starts_at)
  const last = row.all_day ? addDays(dayKey(row.ends_at), -1) : dayKey(row.ends_at)
  const days = []
  for (let d = first; d <= last && days.length < 400; d = addDays(d, 1)) days.push(d)
  return days
}
