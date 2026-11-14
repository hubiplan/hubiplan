import { describe, expect, it } from 'vitest'
import {
  addSub,
  agendaNumbers,
  attach,
  dropBlock,
  moveRow,
  removeRow,
} from '../pages/meetings/agendaTree.ts'
import type { AgendaRow } from '../pages/meetings/agendaTree.ts'

const row = (key: string, level = 0): AgendaRow => ({
  key,
  title: key,
  description: '',
  type: 'other',
  level,
})
const shape = (rows: AgendaRow[]) => rows.map((r) => (r.level ? `-${r.key}` : r.key)).join(' ')

describe('Tagesordnung mit Unterpunkten', () => {
  it('nummeriert Unterpunkte unter ihrem Punkt', () => {
    expect(agendaNumbers([0, 0, 1, 1, 0, 1])).toEqual(['1', '2', '2.1', '2.2', '3', '3.1'])
    // Unterpunkt ganz oben zählt als Punkt
    expect(agendaNumbers([1, 1])).toEqual(['1', '1.1'])
  })

  it('auf einen Punkt gezogen wird zum Unterpunkt dieses Punkts', () => {
    const rows = [row('a'), row('b'), row('c'), row('d')]
    expect(shape(dropBlock(rows, 'd', { kind: 'onto', key: 'b' }))).toBe('a b -d c')
    // ein Punkt mit Unterpunkten nimmt sie mit
    const nested = [row('a'), row('b'), row('b1', 1), row('c')]
    expect(shape(dropBlock(nested, 'b', { kind: 'onto', key: 'c' }))).toBe('a c -b -b1')
    // auf einen Unterpunkt: daneben unter demselben Punkt
    expect(shape(dropBlock(nested, 'c', { kind: 'onto', key: 'b1' }))).toBe('a b -b1 -c')
    // nicht auf sich selbst oder die eigenen Unterpunkte
    expect(dropBlock(nested, 'b', { kind: 'onto', key: 'b1' })).toBe(nested)
  })

  it('zwischen Punkten abgelegt wird eingereiht', () => {
    const rows = [row('a'), row('b'), row('b1', 1), row('b2', 1), row('c')]
    // Unterpunkt vor einen Punkt: wieder eigener Punkt
    expect(shape(dropBlock(rows, 'b2', { kind: 'before', key: 'a' }))).toBe('b2 a b -b1 c')
    expect(shape(dropBlock(rows, 'b1', { kind: 'before', key: null }))).toBe('a b -b2 c b1')
    // zwischen Unterpunkten bleibt er Unterpunkt
    expect(shape(dropBlock(rows, 'c', { kind: 'before', key: 'b2' }))).toBe('a b -b1 -c -b2')
    // ein Punkt springt mit seinen Unterpunkten
    expect(shape(dropBlock(rows, 'b', { kind: 'before', key: 'a' }))).toBe('b -b1 -b2 a c')
  })

  it('verschiebt, hängt um und entfernt', () => {
    const rows = [row('a'), row('b'), row('b1', 1), row('b2', 1), row('c')]
    expect(shape(moveRow(rows, 1, -1))).toBe('b -b1 -b2 a c')
    expect(shape(moveRow(rows, 1, 1))).toBe('a c b -b1 -b2')
    expect(shape(moveRow(rows, 3, -1))).toBe('a b -b2 -b1 c')
    expect(moveRow(rows, 2, -1)).toBe(rows)
    expect(shape(attach(rows, 4, 'a'))).toBe('a -c b -b1 -b2')
    expect(shape(attach(rows, 2, null))).toBe('a b -b2 b1 c')
    expect(shape(removeRow(rows, 1))).toBe('a b1 b2 c')
    expect(shape(addSub(rows, 1, 'neu'))).toBe('a b -b1 -b2 -neu c')
  })
})
