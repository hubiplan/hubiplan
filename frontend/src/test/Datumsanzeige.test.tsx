import { afterEach, describe, expect, it } from 'vitest'
import { formatDate, whenLabel } from '../components/forms.ts'
import { setCatalogForTest } from '../i18n/index.ts'

describe('Datumsanzeige', () => {
  afterEach(() => setCatalogForTest('de'))

  it('zeigt eine Frist im Format der Sprache', () => {
    expect(formatDate('2026-11-19')).toBe('19.11.2026')
    setCatalogForTest('en')
    expect(formatDate('2026-11-19')).toBe('19/11/2026')
  })

  it('zeigt ganztägige Termine ohne Uhrzeit', () => {
    expect(whenLabel('2026-11-18T23:00:00Z', true)).toBe('19.11.2026')
    expect(whenLabel('2026-11-19T17:30:00Z')).toBe('19.11.26, 18:30')
  })
})
