import type { ReactNode } from 'react'
import type { WebsiteData } from '../../api/website.ts'
import { SortHint, SortableList } from '../../components/Sortable.tsx'
import { orgApi } from '../../api/orgs.ts'
import { Checkbox } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

type UnitItem = WebsiteData['units'][number]

/** Untereinheiten unter Webseite › Untereinheiten: bei „ausgewählte“ mit Häkchen, und wer
 *  die Einheit bearbeiten darf, zieht sie hier in die Reihenfolge (je Ebene, wie unter
 *  „Untereinheiten“; sie gilt überall). */
export function UnitList({
  orgId,
  units,
  sortable,
  selected,
  onSelect,
  onReorder,
}: {
  orgId: number
  units: UnitItem[]
  sortable: boolean
  selected: number[] | null
  onSelect: (ids: number[]) => void
  onReorder: () => void
}) {
  const row = (u: UnitItem) =>
    selected === null ? (
      <span>{u.name}</span>
    ) : (
      <Checkbox
        label={u.name}
        checked={selected.includes(u.id)}
        onChange={(on) => onSelect(on ? [...selected, u.id] : selected.filter((id) => id !== u.id))}
      />
    )
  if (!sortable)
    return selected === null ? null : (
      <>
        {units.map((u) => (
          <div key={u.id}>{row(u)}</div>
        ))}
      </>
    )
  const level = (parent: number | null): ReactNode => {
    const children = units.filter((u) => (u.parent ?? null) === parent)
    if (children.length === 0) return null
    return (
      <SortableList
        ariaLabel={parent === null ? t('Reihenfolge') : t('Reihenfolge darunter')}
        items={children}
        id={(u) => u.id}
        label={(u) => u.name}
        onReorder={(ids) => orgApi.reorderDepartments(orgId, parent, ids).then(() => onReorder())}
        render={(u) => (
          <>
            {row(u)}
            {level(u.id)}
          </>
        )}
      />
    )
  }
  return (
    <>
      <SortHint />
      {level(null)}
    </>
  )
}
