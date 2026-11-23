import { describe, expect, it } from 'vitest'
import { keepLegalForm } from '../components/legalForm.ts'

const NB = ' '

describe('keepLegalForm', () => {
  it('bindet „e.V.“ an das letzte Wort', () => {
    expect(keepLegalForm('Schützenverein Musterstadt e.V.')).toBe(
      `Schützenverein Musterstadt${NB}e.V.`,
    )
  })
  it('hält „e. V.“ mit Leerzeichen zusammen', () => {
    expect(keepLegalForm('Musikkapelle Musterdorf e. V.')).toBe(
      `Musikkapelle Musterdorf${NB}e.${NB}V.`,
    )
  })
  it('kennt weitere Rechtsformen', () => {
    expect(keepLegalForm('Sportförderung Musterstadt gGmbH')).toBe(
      `Sportförderung Musterstadt${NB}gGmbH`,
    )
    expect(keepLegalForm('Muster UG (haftungsbeschränkt)')).toBe(
      `Muster${NB}UG${NB}(haftungsbeschränkt)`,
    )
  })
  it('lässt Namen ohne Rechtsform unverändert', () => {
    expect(keepLegalForm('Musikkapelle Musterdorf')).toBe('Musikkapelle Musterdorf')
    expect(keepLegalForm('HUBIplan')).toBe('HUBIplan')
  })
})
