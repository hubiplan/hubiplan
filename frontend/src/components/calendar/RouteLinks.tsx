import type { MapLinks } from '../../api/events.ts'
import { t } from '../../i18n/index.ts'

/** Anfahrt und Routenlinks; öffnen OpenStreetMap bzw. Google Maps in einem neuen Fenster. */
export function RouteLinks({ directions, links }: { directions?: string; links?: MapLinks }) {
  if (!directions && !links?.osm && !links?.google) return null
  return (
    <div className="route-links">
      {directions && <div className="pre-line small">{directions}</div>}
      {(links?.osm || links?.google) && (
        <div className="small">
          {links.osm && (
            <a href={links.osm} target="_blank" rel="noreferrer">
              {t('Route in OpenStreetMap')}
            </a>
          )}
          {links.osm && links.google && ' · '}
          {links.google && (
            <a href={links.google} target="_blank" rel="noreferrer">
              {t('Route in Google Maps')}
            </a>
          )}
        </div>
      )}
    </div>
  )
}
