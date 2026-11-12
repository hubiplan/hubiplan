import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { addMonths } from '../api/qualifications.ts'
import { QualificationsCard } from '../pages/members/QualificationsCard.tsx'
import { fakeApi } from './fakeApi.ts'

const types = [
  {
    id: 1,
    name: 'Erste Hilfe',
    description: '',
    validity_months: 24,
    remind_days: 60,
    inspection_only: false,
    is_archived: false,
    sort_order: 0,
    in_use: true,
  },
  {
    id: 2,
    name: 'Führungszeugnis',
    description: '',
    validity_months: 60,
    remind_days: 90,
    inspection_only: true,
    is_archived: false,
    sort_order: 1,
    in_use: false,
  },
]

const current = {
  id: 5,
  kind: 1,
  kind_name: 'Erste Hilfe',
  inspection_only: false,
  acquired_on: '2024-03-01',
  valid_until: '2026-03-01',
  note: '',
  status: 'expired',
  current: true,
}
const older = { ...current, id: 4, acquired_on: '2020-01-01', valid_until: '2022-01-01' }

describe('Monate addieren wie im Backend', () => {
  it('bleibt am Monatsende im Zielmonat', () => {
    expect(addMonths('2026-01-31', 1)).toBe('2026-02-28')
    expect(addMonths('2024-02-29', 12)).toBe('2025-02-28')
    expect(addMonths('2026-11-12', 26)).toBe('2029-01-12')
  })
})

describe('Qualifikationen in der Mitgliedsakte', () => {
  it('zeigt Stand und Verlauf und schlägt beim Eintragen das Ablaufdatum vor', async () => {
    const calls = fakeApi({
      'GET /api/orgs/7/members/9/qualifications/': () => ({
        status: 200,
        body: [current, { ...older, current: false }],
      }),
      'GET /api/orgs/7/qualification-types/': () => ({ status: 200, body: types }),
      'POST /api/orgs/7/members/9/qualifications/': () => ({ status: 201, body: current }),
    })
    render(<QualificationsCard orgId={7} memberId={9} canEdit />)
    expect(await screen.findByText('abgelaufen')).toBeInTheDocument()
    expect(screen.getByText('Frühere Nachweise (1)')).toBeInTheDocument()
    const user = userEvent.setup()
    await screen.findByRole('option', { name: 'Erste Hilfe' })
    const form = screen.getByRole('form', { name: 'Qualifikation eintragen' })
    await user.selectOptions(within(form).getByLabelText('Qualifikation'), '1')
    const from = within(form).getByLabelText('erworben am')
    await user.clear(from)
    await user.type(from, '2025-05-31')
    expect(within(form).getByLabelText('gültig bis (leer: unbefristet)')).toHaveValue('2027-05-31')
    await user.type(within(form).getByLabelText('Bemerkung'), 'DRK')
    await user.click(within(form).getByRole('button', { name: 'Eintragen' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key.startsWith('POST'))).toBe(true))
    const post = calls.find((c) => c.key.startsWith('POST'))!
    expect(JSON.parse(String(post.init?.body))).toEqual({
      kind: 1,
      acquired_on: '2025-05-31',
      valid_until: '2027-05-31',
      note: 'DRK',
    })
  })

  it('hat beim Einsichtsvermerk kein Bemerkungsfeld', async () => {
    fakeApi({
      'GET /api/orgs/7/members/9/qualifications/': () => ({ status: 200, body: [] }),
      'GET /api/orgs/7/qualification-types/': () => ({ status: 200, body: types }),
    })
    render(<QualificationsCard orgId={7} memberId={9} canEdit />)
    await screen.findByRole('option', { name: 'Führungszeugnis' })
    const user = userEvent.setup()
    const form = screen.getByRole('form', { name: 'Qualifikation eintragen' })
    await user.selectOptions(within(form).getByLabelText('Qualifikation'), '2')
    expect(within(form).getByLabelText('eingesehen am')).toBeInTheDocument()
    expect(within(form).queryByLabelText('Bemerkung')).toBeNull()
    expect(within(form).getByText(/nie der Inhalt/)).toBeInTheDocument()
  })
})
