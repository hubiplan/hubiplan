// Tagesordnung mit Unterpunkten (Ralf 14.11.2026): eine flache Liste, in der jeder Punkt
// eine Ebene hat (0 = Punkt, 1 = Unterpunkt des Punkts davor). Daraus entstehen die
// Nummern 8, 8.1, 8.2 … wie im Backend (meetings.models.agenda_numbers).
import type { AgendaItem } from '../../api/meetings.ts'

export type AgendaRow = AgendaItem & { key: string; level: number }

/** Nummern zu den Ebenen; ein Unterpunkt ganz oben zählt als Punkt. */
export function agendaNumbers(levels: number[]): string[] {
  let top = 0
  let sub = 0
  return levels.map((level) => {
    if (level && top) {
      sub += 1
      return `${top}.${sub}`
    }
    top += 1
    sub = 0
    return String(top)
  })
}

/** Erster Punkt ist nie Unterpunkt. */
export function normalize(rows: AgendaRow[]): AgendaRow[] {
  return rows.map((row, i) => (i === 0 && row.level ? { ...row, level: 0 } : row))
}

/** Ende (ausschließlich) des Blocks ab i: ein Punkt mit seinen Unterpunkten. */
export function blockEnd(rows: AgendaRow[], i: number): number {
  if (rows[i]?.level) return i + 1
  let j = i + 1
  while (j < rows.length && rows[j].level) j += 1
  return j
}

/** Punkt, zu dem der Unterpunkt i gehört (oder -1). */
export function parentIndex(rows: AgendaRow[], i: number): number {
  if (!rows[i]?.level) return -1
  for (let j = i - 1; j >= 0; j -= 1) if (!rows[j].level) return j
  return -1
}

/**
 * Block ab `from` an die Stelle `to` der übrigen Zeilen setzen, mit neuer Ebene.
 * Ein Punkt mit Unterpunkten, der selbst Unterpunkt wird, nimmt sie als Unterpunkte mit
 * (es gibt nur eine Ebene darunter).
 */
export function placeBlock(rows: AgendaRow[], from: number, to: number, level: number) {
  const end = blockEnd(rows, from)
  const block = rows.slice(from, end)
  const rest = [...rows.slice(0, from), ...rows.slice(end)]
  const at = Math.max(0, Math.min(to, rest.length))
  const lvl = at === 0 ? 0 : level ? 1 : 0
  const moved = block.map((row, i) => ({ ...row, level: i === 0 ? lvl : lvl ? 1 : row.level }))
  rest.splice(at, 0, ...moved)
  return normalize(rest)
}

/** Nach oben/unten: ein Punkt springt mit seinen Unterpunkten über den Nachbarpunkt,
 *  ein Unterpunkt tauscht mit dem Unterpunkt daneben. */
export function moveRow(rows: AgendaRow[], i: number, by: -1 | 1): AgendaRow[] {
  const row = rows[i]
  if (!row) return rows
  if (row.level) {
    const j = i + by
    if (!rows[j]?.level) return rows
    const next = [...rows]
    next[i] = rows[j]
    next[j] = row
    return next
  }
  if (by < 0) {
    let p = i - 1
    while (p >= 0 && rows[p].level) p -= 1
    if (p < 0) return rows
    return placeBlock(rows, i, p, 0)
  }
  const end = blockEnd(rows, i)
  if (end >= rows.length) return rows
  const nextEnd = blockEnd(rows, end)
  // Stelle in der Liste ohne den eigenen Block
  return placeBlock(rows, i, nextEnd - (end - i), 0)
}

export function canMove(rows: AgendaRow[], i: number, by: -1 | 1): boolean {
  return moveRow(rows, i, by) !== rows
}

/** Unter einen anderen Punkt hängen (parentKey) oder zurück auf die oberste Ebene (null). */
export function attach(rows: AgendaRow[], i: number, parentKey: string | null): AgendaRow[] {
  const row = rows[i]
  if (!row) return rows
  if (parentKey === null) {
    if (!row.level) return rows
    const p = parentIndex(rows, i)
    const rest = [...rows.slice(0, i), ...rows.slice(i + 1)]
    // hinter den Block des bisherigen Punkts, damit dessen übrige Unterpunkte bleiben
    const end = blockEnd(rest, p)
    rest.splice(end, 0, { ...row, level: 0 })
    return normalize(rest)
  }
  const end = blockEnd(rows, i)
  const rest = [...rows.slice(0, i), ...rows.slice(end)]
  const p = rest.findIndex((r) => r.key === parentKey && !r.level)
  if (p < 0) return rows
  return placeBlock(rows, i, blockEnd(rest, p), 1)
}

/** Entfernen; Unterpunkte eines entfernten Punkts werden zu eigenen Punkten. */
export function removeRow(rows: AgendaRow[], i: number): AgendaRow[] {
  const end = blockEnd(rows, i)
  return normalize(
    rows.flatMap((row, j) =>
      j === i ? [] : !rows[i].level && j > i && j < end ? [{ ...row, level: 0 }] : [row],
    ),
  )
}

/** Neuen Unterpunkt am Ende der Unterpunkte von i anlegen. */
export function addSub(rows: AgendaRow[], i: number, key: string): AgendaRow[] {
  const parent = rows[i]
  if (!parent || parent.level) return rows
  const end = blockEnd(rows, i)
  const next = [...rows]
  next.splice(end, 0, { key, title: '', description: '', type: parent.type, level: 1 })
  return next
}

/** Ziel beim Ziehen: auf einen Punkt (wird dessen Unterpunkt) oder vor einen Punkt (null = ans Ende). */
export type DropTarget = { kind: 'onto'; key: string } | { kind: 'before'; key: string | null }

/** Gezogenen Block ablegen (Ralf 14.11.: auf einen Punkt gezogen = dessen Unterpunkt). */
export function dropBlock(rows: AgendaRow[], fromKey: string, target: DropTarget): AgendaRow[] {
  const from = rows.findIndex((r) => r.key === fromKey)
  if (from < 0) return rows
  const end = blockEnd(rows, from)
  const inBlock = new Set(rows.slice(from, end).map((r) => r.key))
  if (target.key !== null && inBlock.has(target.key)) return rows
  const rest = [...rows.slice(0, from), ...rows.slice(end)]
  let to: number
  let level: number
  if (target.kind === 'onto') {
    const t = rest.findIndex((r) => r.key === target.key)
    if (t < 0) return rows
    if (rest[t].level) {
      // auf einen Unterpunkt: neuer Unterpunkt desselben Punkts direkt dahinter
      to = t + 1
    } else {
      to = blockEnd(rest, t)
    }
    level = 1
  } else {
    to = target.key === null ? rest.length : rest.findIndex((r) => r.key === target.key)
    if (to < 0) return rows
    // zwischen Unterpunkten bleibt er Unterpunkt, sonst eigener Punkt
    level = rest[to]?.level ? 1 : 0
  }
  const next = placeBlock(rows, from, to, level)
  const shape = (list: AgendaRow[]) => list.map((r) => `${r.key}:${r.level}`).join(',')
  return shape(next) === shape(rows) ? rows : next
}
