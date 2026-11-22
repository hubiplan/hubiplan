import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import werte from '../theme/werte.json'

// Web und Apps sollen wie aus einem Guss wirken: Markenfarben, Rundungen und Schriftstufen
// stehen in theme/werte.json und müssen zu den Variablen in theme.css passen.
const css = readFileSync(resolve(__dirname, '../theme/theme.css'), 'utf8')

function variable(name: string): string {
  const treffer = css.match(new RegExp(`${name}:\\s*([^;]+);`))
  if (!treffer) throw new Error(`Variable ${name} fehlt in theme.css`)
  return treffer[1].trim()
}

const rem = (px: number) => `${px / 16}rem`

describe('Gestaltungswerte wie in den Apps', () => {
  it('Markenfarben', () => {
    expect(variable('--color-primary')).toBe(werte.marke.primaer)
    expect(variable('--color-accent')).toBe(werte.marke.akzent)
  })

  it('Rundungen', () => {
    expect(variable('--radius-sm')).toBe(rem(werte.radius.klein))
    expect(variable('--radius')).toBe(rem(werte.radius.normal))
    expect(variable('--radius-lg')).toBe(rem(werte.radius.gross))
    expect(variable('--radius-sheet')).toBe(rem(werte.radius.blatt))
  })

  it('Schriftstufen', () => {
    expect(variable('--font-size-title-lg')).toBe(rem(werte.schrift.titelGross))
    expect(variable('--font-size-title')).toBe(rem(werte.schrift.titel))
    expect(variable('--font-size-section')).toBe(rem(werte.schrift.ueberschrift))
    expect(variable('--font-size-text')).toBe(rem(werte.schrift.text))
    expect(variable('--font-size-small')).toBe(rem(werte.schrift.klein))
    expect(variable('--font-size-label')).toBe(rem(werte.schrift.marke))
  })
})
