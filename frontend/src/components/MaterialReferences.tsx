import { Link } from 'react-router-dom'
import { useOrg } from '../org/OrgContext.tsx'
import { t } from '../i18n/index.ts'
import { materialApi } from '../api/materials.ts'
import { useLoad } from './forms.ts'

export function MaterialReferences({
  kind,
  id,
  originalStart,
  sourceBase,
  level = 3,
}: {
  kind: 'member' | 'event' | 'todo' | 'document'
  id: number
  originalStart?: string
  sourceBase?: string
  /** Überschriftenebene passend zur Seite (Mitgliedsakte: 2) */
  level?: 2 | 3
}) {
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
  return (
    <References
      key={`${prefix}-${query}`}
      base={`${prefix}materials/`}
      query={query.toString()}
      level={level}
    />
  )
}

function References({ base, query, level }: { base: string; query: string; level: 2 | 3 }) {
  const Heading = level === 2 ? 'h2' : 'h3'
  const { data, error } = useLoad(() => materialApi.list(base, query), [base, query])
  return (
    <section className="card">
      <Heading>{t('Zugeordnetes Material')}</Heading>
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
