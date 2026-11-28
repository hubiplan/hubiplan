import type { ReactNode } from 'react'
import type { HomeSectionData, SectionOptions } from '../../api/website.ts'
import { SortHint } from '../../components/Sortable.tsx'
import { Checkbox } from '../../components/ui.tsx'
import { useSortable } from '../../components/useSortable.tsx'
import { t } from '../../i18n/index.ts'

export function ContactsField({
  data,
  value,
  setData,
  titleField,
}: {
  data: SectionOptions
  value: HomeSectionData
  setData: (patch: Partial<HomeSectionData>) => void
  titleField: ReactNode
}) {
  const roles = data.home_choices?.roles ?? []
  const chosen = value.roles ?? []
  const name = new Map(roles.map((r) => [r.id, r.name]))
  const items = chosen.filter((id) => name.has(id))
  const sortable = useSortable({
    items,
    id: (id) => id,
    label: (id) => name.get(id) ?? '',
    onReorder: async (order) => setData({ roles: order }),
  })
  return (
    <>
      {titleField}
      <p className="muted small">
        {t(
          'Bis zu vier Rollen, die auf der Webseite stehen. Personen erscheinen nur mit Einwilligung, wie auf der Vorstandsseite.',
        )}
      </p>
      {roles.length === 0 && (
        <p className="muted">{t('Keine Rolle ist für die Webseite freigegeben.')}</p>
      )}
      {roles.map((r) => (
        <Checkbox
          key={r.id}
          label={r.name}
          checked={chosen.includes(r.id)}
          disabled={!chosen.includes(r.id) && chosen.length >= 4}
          onChange={(on) =>
            setData({ roles: on ? [...chosen, r.id] : chosen.filter((x) => x !== r.id) })
          }
        />
      ))}
      {items.length > 1 && (
        <>
          <SortHint />
          <ul className="sortable-list" aria-label={t('Reihenfolge der Ansprechpartner')}>
            {sortable.ordered.map((id) => {
              const { ref, className } = sortable.rowProps(id)
              return (
                <li key={id} ref={ref} className={className}>
                  {sortable.handle(id)}
                  <div className="sortable-label">{name.get(id)}</div>
                </li>
              )
            })}
          </ul>
          {sortable.status}
        </>
      )}
    </>
  )
}
