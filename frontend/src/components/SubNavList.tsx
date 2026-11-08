// Unterpunkte eines Menüpunkts in der Seitenleiste. Punkte mit Arbeitsgruppe (Finanzen,
// Konzept S-01) erscheinen als aufklappbare Gruppen: Die Gruppe der aktuellen Seite ist
// offen, ▸ öffnet eine andere zum Nachsehen (eine zur Zeit). Eine Gruppe mit nur einem
// Eintrag erscheint als einfacher Eintrag.
import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { activeGroup, groupNodes } from './subnav.ts'
import type { NavNode } from './subnav.ts'

export function SubNavList({
  nodes,
  pathname,
  onChoose,
}: {
  nodes: NavNode[]
  pathname: string
  onChoose: () => void
}) {
  const current = activeGroup(nodes, pathname)
  // Eine andere Gruppe zum Nachsehen; die eigene lässt sich zuklappen. Beides gilt nur
  // für die Seite, auf der es gewählt wurde.
  const [state, setState] = useState<{ path: string; peek: string | null; ownClosed: boolean }>({
    path: pathname,
    peek: null,
    ownClosed: false,
  })
  const fresh = state.path === pathname
  const peek = fresh ? state.peek : null
  const ownClosed = fresh && state.ownClosed
  const baseId = useId()

  const renderItems = (list: NavNode[], level: number): ReactNode =>
    list.map((c) => (
      <li key={c.to}>
        <NavLink to={c.to} end={c.end} className="sidebar-sublink" onClick={onChoose}>
          {c.label}
        </NavLink>
        {c.children.length > 0 &&
          (pathname === c.to || pathname.startsWith(`${c.to}/`) || level > 1) && (
            <ul className="sidebar-sub sidebar-sub-deep">{renderItems(c.children, level + 1)}</ul>
          )}
      </li>
    ))

  if (nodes.length === 0) return null
  return (
    <ul className="sidebar-sub">
      {groupNodes(nodes).map((b) => {
        if (b.kind === 'item') return renderItems([b.node], 1)
        const own = b.key === current
        const open = own ? !ownClosed : peek === b.key
        const listId = `${baseId}-${b.key}`
        return (
          <li key={`g:${b.key}`} className={`sidebar-nav-group${own ? ' current' : ''}`}>
            <button
              type="button"
              className="sidebar-group-toggle"
              aria-expanded={open}
              aria-controls={listId}
              onClick={() => {
                setState(
                  own
                    ? { path: pathname, peek, ownClosed: !ownClosed }
                    : { path: pathname, peek: peek === b.key ? null : b.key, ownClosed },
                )
              }}
            >
              <span>{b.label}</span>
              <span className="sidebar-group-caret" aria-hidden="true">
                ▸
              </span>
            </button>
            <ul className="sidebar-sub sidebar-group-items" id={listId} hidden={!open}>
              {renderItems(b.nodes, 1)}
            </ul>
          </li>
        )
      })}
    </ul>
  )
}
