import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { PerformanceOverview } from '../pages/music/PerformanceOverview.tsx'
import { fakeApi } from './fakeApi.ts'
import { todayIso } from '../api/members.ts'

vi.mock('../org/OrgContext.tsx', () => ({ useActiveOrg: () => ({ id: 7 }) }))

it('zeigt Handlungsbedarf mit direkten Links und ohne Finanzhinweise ohne Leserecht', async () => {
  const day = (offset: number) => {
    const date = new Date(`${todayIso()}T12:00:00Z`)
    date.setUTCDate(date.getUTCDate() + offset)
    return date.toISOString().slice(0, 10)
  }
  fakeApi({
    [`GET /api/orgs/7/music/performances/overview/?start=${day(-90)}&end=${day(180)}&page=1`]:
      () => ({
        status: 200,
        body: {
          count: 1,
          next: null,
          previous: null,
          finance_visible: false,
          results: [
            {
              id: 9,
              title: 'Musterkonzert',
              starts_at: '2026-12-01T18:00:00Z',
              ends_at: '2026-12-01T20:00:00Z',
              location: 'Musterhalle',
              status: 'critical',
              required: 3,
              accepted: 1,
              pending: 1,
              issues: [
                { code: 'missing_players', count: 2, area: 'staffing', level: 'critical' },
                { code: 'missing_scores', count: 1, area: 'program', level: 'critical' },
              ],
            },
          ],
        },
      }),
  })
  render(
    <MemoryRouter>
      <PerformanceOverview />
    </MemoryRouter>,
  )
  expect(await screen.findByText('Musterkonzert')).toBeInTheDocument()
  expect(screen.getByText('Handlungsbedarf')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Fehlende Zusagen für Sollplätze: 2' })).toHaveAttribute(
    'href',
    '/musik?besetzung=9',
  )
  expect(screen.getByRole('link', { name: 'Fehlende Notenexemplare: 1' })).toHaveAttribute(
    'href',
    '/musik?programm=9',
  )
  expect(screen.queryByRole('link', { name: 'Auftrittsabrechnung' })).not.toBeInTheDocument()
})
