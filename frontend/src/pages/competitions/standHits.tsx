// Erfassen am Stand: Treffer der Suche (Starter, Mitglied oder neuer Gast) und ihre Anzeige.
import {
  showValue,
  type MemberChoice,
  type Scoring,
  type Starter,
  type TargetInfo,
} from '../../api/competitions.ts'
import { t } from '../../i18n/index.ts'

export type Hit =
  | { kind: 'starter'; starter: Starter }
  | { kind: 'member'; member: MemberChoice }
  | { kind: 'guest'; name: string }

export function hitKey(h: Hit) {
  if (h.kind === 'starter') return `s-${h.starter.key ?? h.starter.id}`
  if (h.kind === 'member') return `m-${h.member.membership}`
  return 'gast'
}

export function hitName(h: Hit) {
  if (h.kind === 'starter') return h.starter.name
  if (h.kind === 'member') return h.member.name
  return h.name
}

export function hitLabel(h: Hit, scoring: Scoring) {
  if (h.kind === 'starter') {
    const v = h.starter.values[String(scoring.id)]
    return (
      <>
        <strong>{h.starter.name}</strong>
        <span className="muted"> {h.starter.unit_name || h.starter.club}</span>
        {v ? (
          <span className="push-right">
            {t('schon')} {showValue(v, scoring.decimals)}
          </span>
        ) : null}
      </>
    )
  }
  if (h.kind === 'member')
    return (
      <>
        <strong>{h.member.name}</strong>
        <span className="muted">
          {' '}
          {h.member.unit_name}
          {h.member.birth_year ? t(' · {birth_year}', { birth_year: h.member.birth_year }) : ''}
        </span>
        <span className="push-right muted">{t('neu')}</span>
      </>
    )
  return (
    <>
      {t('Neu:')} <strong>„{h.name}“</strong> {t('als Gast hinzufügen')}
    </>
  )
}

/**
 * Spiegel / äußerster Ring für die Live-Kamera; bei Karten mit einem Spiegel und bei der
 * Fünf-Spiegel-Karte (vier Ecken und Mitte, Ralf 09.11.).
 */
export function blackShare(tm: TargetInfo): number | null {
  return tm.black_diameter && tm.rings[0] && (tm.spots === 1 || tm.spots === 5)
    ? tm.black_diameter / tm.rings[0].diameter
    : null
}
