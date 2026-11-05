import { render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { channelLabel } from '../api/circulars.ts'
import { FIELD_TYPES } from '../api/fields.ts'
import { DATE_PRECISION_WORD, formatDate } from '../components/forms.ts'
import { setCatalogForTest } from '../i18n/index.ts'
import en from '../i18n/en.json'
import { StatusMessage } from '../components/ui.tsx'

afterEach(() => setCatalogForTest('de'))
it('übersetzt dynamische Systemauswahlen nach dem Sprachwechsel, technische Codes bleiben gleich', () => {
  setCatalogForTest('en', en)
  expect(channelLabel.letter).toBe('Letter')
  expect(channelLabel.portal).toBe('member area only')
  expect(DATE_PRECISION_WORD.month).toBe('exact month')
  expect(FIELD_TYPES.find((f) => f.value === 'number')?.label).toBe('Number')
  expect(FIELD_TYPES.find((f) => f.value === 'date')?.label).toBe('Date')
  expect(formatDate('2026-11-05')).toBe('05/11/2026')
  setCatalogForTest('de')
  expect(channelLabel.letter).toBe('Brief')
  expect(DATE_PRECISION_WORD.month).toBe('monatsgenau')
})
it('hält den Statusknoten für aufeinanderfolgende Aktionen bestehen', () => {
  const { rerender } = render(<StatusMessage message={null} />)
  const status = screen.getByRole('status')
  rerender(<StatusMessage message="Gespeichert." />)
  expect(screen.getByRole('status')).toBe(status)
  expect(status).toHaveAttribute('aria-atomic', 'true')
  rerender(<StatusMessage message={null} />)
  expect(status).toHaveTextContent('')
  rerender(<StatusMessage message="Gespeichert." />)
  expect(screen.getByRole('status')).toBe(status)
  expect(status).toHaveTextContent('Gespeichert.')
})
