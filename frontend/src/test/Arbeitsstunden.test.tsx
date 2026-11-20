import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { WorkHoursCard } from '../pages/billing/WorkHours.tsx'
import { feeRunChecks } from '../learning/checks.ts'
import { fakeApi } from './fakeApi.ts'

const B = '/api/orgs/7/billing'
const data = (over = {}) => ({
  helpers_on: true,
  min_age: null,
  max_age: null,
  years: [
    { year: 2026, label: '2026' },
    { year: 2025, label: '2025' },
  ],
  rows: [
    { member_type: 1, name: 'aktiv', active: true, hours: '10.00', rate: '15.00' },
    { member_type: 2, name: 'passiv', active: false, hours: null, rate: null },
  ],
  ...over,
})

describe('Arbeitsstunden', () => {
  it('speichert Pflichtstunden, Ersatz und Altersgrenzen von selbst und zeigt den Stand', async () => {
    const calls = fakeApi({
      [`GET ${B}/work-hours/`]: () => ({ status: 200, body: data() }),
      [`PUT ${B}/work-hours/`]: () => ({ status: 200, body: data({ max_age: 65 }) }),
      [`GET ${B}/work-hours/balance/?jahr=2026`]: () => ({
        status: 200,
        body: {
          year: 2026,
          label: '2026',
          people: [
            {
              membership: 3,
              name: 'Muster, Erika',
              member_type: 'aktiv',
              required: '10.00',
              done: '6.50',
              missing: '3.50',
              amount: '52.50',
            },
          ],
          total: '52.50',
        },
      }),
    })
    render(
      <MemoryRouter>
        <WorkHoursCard orgId={7} canEdit />
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    expect(await screen.findByLabelText('aktiv: Pflichtstunden im Jahr')).toHaveValue('10')
    expect(screen.getByLabelText('passiv: Ersatz je fehlender Stunde (€)')).toBeDisabled()
    await user.type(screen.getByLabelText('passiv: Pflichtstunden im Jahr'), '2,5')
    await user.type(screen.getByLabelText('Pflicht bis Alter'), '65')
    // Autospeichern, kein Knopf
    expect(await screen.findByText('✓ Gespeichert', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Speichern' })).toBeNull()
    const put = calls.filter((c) => c.key === `PUT ${B}/work-hours/`).at(-1)!
    expect(JSON.parse(String(put.init?.body))).toEqual({
      min_age: null,
      max_age: 65,
      rows: [
        { member_type: 1, hours: '10', rate: '15' },
        { member_type: 2, hours: '2.5', rate: null },
      ],
    })
    await user.click(screen.getByText('Stand je Mitglied'))
    expect(await screen.findByText('Muster, Erika')).toBeInTheDocument()
  })

  it('weist ohne Helferdienste auf das Modul hin', async () => {
    fakeApi({
      [`GET ${B}/work-hours/`]: () => ({ status: 200, body: data({ helpers_on: false }) }),
    })
    render(
      <MemoryRouter>
        <WorkHoursCard orgId={7} canEdit={false} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: 'Module einstellen' })).toBeInTheDocument()
    expect(screen.queryByText('Stand je Mitglied')).not.toBeInTheDocument()
  })

  it('nennt den Ersatzbeitrag in der Prüfliste vor dem Beitragslauf', () => {
    const items = feeRunChecks({
      skipped: [],
      members: 3,
      dueDays: 14,
      accountWithIban: true,
      sepaEnabled: false,
      checks: {
        unreachable: 0,
        with_mandate: 0,
        open_change_requests: 0,
        work_year: 2025,
        work_count: 2,
        work_total: '90.00',
      },
    })
    const item = items.find((i) => i.key === 'work_hours')
    expect(item?.text).toContain('2 Mitglieder haben 2025 zu wenige Arbeitsstunden geleistet')
  })
})
