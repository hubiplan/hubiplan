import { Link } from 'react-router-dom'
import { useOrg } from '../org/OrgContext.tsx'
import { t } from '../i18n/index.ts'
import { materialApi } from '../api/materials.ts'
import { useLoad } from './forms.ts'
import { EventRow } from './calendar/EventRow.tsx'

export function MaterialReferences({
  kind,
  id,
  originalStart,
  sourceBase,
  level = 3,
  title,
  wide = false,
}: {
  kind: 'member' | 'event' | 'todo' | 'document'
  id: number
  originalStart?: string
  sourceBase?: string
  /** Überschriftenebene passend zur Seite (Mitgliedsakte: 2) */
  level?: 2 | 3
  /** Eigene Überschrift, z. B. „Ausgegebenes Material“ in der Mitgliedsakte */
  title?: string
  wide?: boolean
}) {
  const scope = useMaterialScope(kind, id, originalStart, sourceBase)
  if (!scope) return null
  const { prefix, query } = scope
  return (
    <References
      key={`${prefix}-${query}`}
      base={`${prefix}materials/`}
      query={query.toString()}
      level={level}
      title={title ?? t('Zugeordnetes Material')}
      wide={wide}
    />
  )
}

/** Ob und wo Material zu diesem Datensatz abgefragt wird (Modul, Recht, gleiche Einheit). */
function useMaterialScope(
  kind: 'member' | 'event' | 'todo' | 'document',
  id: number,
  originalStart?: string,
  sourceBase?: string,
): { prefix: string; query: URLSearchParams } | null {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('material') : activeDept?.material_enabled
  const prefix = active ? `/api/orgs/${active.id}/` : `/api/depts/${activeDept?.id}/`
  if (
    !enabled ||
    !permissions.includes('material.view') ||
    (sourceBase && !sourceBase.startsWith(prefix))
  )
    return null
  const query = new URLSearchParams({ [kind]: String(id) })
  if (originalStart) query.set('original_start', originalStart)
  return { prefix, query }
}

/** Material als Zeile im Block „Zu diesem Termin“: zugeordnete Stücke und Verweis zur Übersicht. */
export function EventMaterialRow({
  id,
  originalStart,
  sourceBase,
}: {
  id: number
  originalStart?: string
  sourceBase?: string
}) {
  const scope = useMaterialScope('event', id, originalStart, sourceBase)
  if (!scope) return null
  const query = scope.query.toString()
  return (
    <MaterialRowBody
      key={`${scope.prefix}-${query}`}
      base={`${scope.prefix}materials/`}
      query={query}
    />
  )
}

function MaterialRowBody({ base, query }: { base: string; query: string }) {
  const { data, error } = useLoad(() => materialApi.list(base, query), [base, query])
  return (
    <EventRow
      label={t('Material')}
      actions={
        <Link className="button button-ghost" to={`/material?${query}`}>
          {t('Materialübersicht')}
        </Link>
      }
    >
      {error && <p role="alert">{error}</p>}
      {data && data.items.length === 0 && (
        <span className="muted small">{t('nichts zugeordnet')}</span>
      )}
      {data && data.items.length > 0 && (
        <ul className="plain-list">
          {data.items.map((item) => (
            <li key={item.id}>
              <Link to={`/material/${item.id}`}>
                {item.inventory_number} · {item.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </EventRow>
  )
}

function References({
  base,
  query,
  level,
  title,
  wide,
}: {
  base: string
  query: string
  level: 2 | 3
  title: string
  wide: boolean
}) {
  const Heading = level === 2 ? 'h2' : 'h3'
  const { data, error } = useLoad(() => materialApi.list(base, query), [base, query])
  return (
    <section className={wide ? 'card card-wide' : 'card'}>
      <Heading>{title}</Heading>
      {error && <p role="alert">{error}</p>}
      {data?.items.map((item) => (
        <p key={item.id}>
          <Link to={`/material/${item.id}`}>
            {item.inventory_number} · {item.title}
          </Link>
        </p>
      ))}
      <Link to={`/material?${query}`}>{t('Materialübersicht öffnen')}</Link>
    </section>
  )
}
