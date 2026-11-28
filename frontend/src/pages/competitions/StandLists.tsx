// Erfassen am Stand: die beiden Listen unter der Eingabe, „Zuletzt erfasst“ und „Noch offen“.
// Ein Klick auf einen Namen wählt den Schützen zur Eingabe aus.
import { showValue, type Scoring, type Starter } from '../../api/competitions.ts'
import { t } from '../../i18n/index.ts'
import type { useStandStore } from './standStore.ts'

export function StandLists({
  local,
  scoring,
  fullscreen,
  onChoose,
}: {
  local: ReturnType<typeof useStandStore>['local']
  scoring: Scoring
  fullscreen: boolean
  onChoose: (starter: Starter) => void
}) {
  const open = local.starters.filter((s) => !s.values[String(scoring.id)])
  // Zuletzt erfasst über alle Geräte: Zeitpunkt vom Server, dazu eigene noch nicht
  // abgeglichene Eingaben; je Schütze nur die letzte mit seinem aktuellen Wert
  const latest = new Map<number | string, { ref: number | string; name: string; at: string }>()
  for (const s of local.starters)
    if (s.scored_at && s.values[String(scoring.id)])
      latest.set(s.key ?? s.id, { ref: s.key ?? s.id, name: s.name, at: s.scored_at })
  for (const r of local.recent) {
    const known = latest.get(r.ref)
    if (!known || Date.parse(r.at) > Date.parse(known.at))
      latest.set(r.ref, { ref: r.ref, name: r.name, at: r.at })
  }
  const recent = [...latest.values()]
    .map((r) => {
      const s = local.starters.find((x) => (x.key ?? x.id) === r.ref)
      return { ...r, value: s?.values[String(scoring.id)] ?? '' }
    })
    .filter((r) => r.value !== '')
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, 10)

  return (
    <>
      <details className="stand-section" open={!fullscreen || undefined}>
        <summary>{t('Zuletzt erfasst ({n})', { n: recent.length })}</summary>
        <ul className="stand-list">
          {recent.map((r) => (
            <li key={`${r.ref}-${r.at}`}>
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  const s = local.starters.find((x) => (x.key ?? x.id) === r.ref)
                  if (s) onChoose(s)
                }}
              >
                {r.name}
              </button>{' '}
              <span className="push-right">{showValue(r.value, scoring.decimals)}</span>
            </li>
          ))}
        </ul>
      </details>
      <details className="stand-section">
        <summary>{t('Noch offen ({n})', { n: open.length })}</summary>
        <ul className="stand-list">
          {open.map((s) => (
            <li key={s.key ?? s.id}>
              <button type="button" className="link-button" onClick={() => onChoose(s)}>
                {s.name}
              </button>
              <span className="muted"> {s.unit_name || s.club}</span>
            </li>
          ))}
        </ul>
      </details>
    </>
  )
}
