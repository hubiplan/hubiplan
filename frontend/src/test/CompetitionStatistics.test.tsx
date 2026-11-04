import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { CompetitionStatistics } from '../pages/competitions/Statistics.tsx'
import type { CompetitionStatisticsData } from '../api/competitionStatistics.ts'
import { fakeApi } from './fakeApi.ts'

const base = '/api/orgs/7/competitions/statistics/'
const group = {
  id: 'a'.repeat(24),
  label: 'LG 10 m · beste 3 von 5 · Ringe',
  method: 'ringe',
  unit_label: 'Ringe',
  counted_shots: 3,
  maximum: 30,
  higher_better: true,
}
const sample: CompetitionStatisticsData = {
  years: [2026, 2025],
  groups: [group],
  selected_group: group,
  summary: { competitions: 3, members: 2, starts: 6, wins: 2, podiums: 5, prizes: 0, awards: 0 },
  performance: {
    count: 5,
    average: 23.8,
    member_average: 23,
    per_shot: 23.8 / 3,
    best: 30,
    best_names: ['Anna Weber'],
    previous_year: 2025,
    previous_average: 21,
    change: 4.67,
  },
  group_summary: [],
  buckets: [
    { year: 2025, starts: 2, members: 2, count: 2, average: 21 },
    { year: 2026, starts: 4, members: 2, count: 3, average: 25.67 },
  ],
  members: [
    {
      membership: 11,
      name: 'Anna Weber',
      starts: 3,
      wins: 2,
      podiums: 3,
      prizes: 0,
      count: 3,
      average: 27,
      best: 30,
    },
  ],
  member_options: [
    { membership: 11, name: 'Anna Weber' },
    { membership: 12, name: 'Bernd Müller' },
  ],
  results: [
    {
      competition: 3,
      title: 'Herbstschießen',
      date: '2026-09-01',
      form: 'rangliste',
      own: true,
      membership: 11,
      name: 'Anna Weber',
      unit_name: '',
      scoring: 'Einzelwertung',
      scoring_id: 30,
      group: group.id,
      value: 27,
      unit_label: 'Ringe',
      place: 1,
      field: 20,
    },
  ],
  awards: [],
  can_open: true,
}

function Location() {
  const [params] = useSearchParams()
  return <output aria-label="Auswahl">{params.toString()}</output>
}

describe('Wettbewerbsstatistik', () => {
  it('zeigt Ringdurchschnitt, Mitgliederdurchschnitt und die Berechnungsbasis', async () => {
    fakeApi({ [`GET ${base}`]: () => ({ status: 200, body: sample }) })
    render(
      <MemoryRouter>
        <CompetitionStatistics org={7} />
      </MemoryRouter>,
    )
    const average = await screen.findByRole('heading', {
      name: 'Durchschnittliche Ringe',
    })
    expect(average.closest('.tile')).toHaveTextContent('23,8 Ringe')
    expect(average.closest('.tile')).toHaveTextContent('Aus 5 gültigen Ergebnissen')
    expect(
      screen.getByRole('heading', { name: 'Mitgliederdurchschnitt' }).closest('.tile'),
    ).toHaveTextContent('23 Ringe')
    expect(
      screen.getByRole('heading', { name: 'Ringe pro gewertetem Schuss' }).closest('.tile'),
    ).toHaveTextContent('7,93')
    expect(screen.getAllByText('Werte als Tabelle')).toHaveLength(2)
  })

  it('öffnet ein Mitglied und erhält Zeitraum, Wertung und den Bereich der Mitgliedsakte', async () => {
    const calls = fakeApi({
      [`GET ${base}?year=2026&group=${group.id}`]: () => ({ status: 200, body: sample }),
      [`GET ${base}?year=2026&group=${group.id}&membership=11`]: () => ({
        status: 200,
        body: { ...sample, performance: { ...sample.performance, average: 28.5 } },
      }),
    })
    render(
      <MemoryRouter
        initialEntries={[`/?bereich=wettbewerbe&stat_jahr=2026&stat_wertung=${group.id}`]}
      >
        <CompetitionStatistics org={7} />
        <Location />
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Anna Weber' }))
    expect(await screen.findByRole('heading', { name: 'Einzelergebnisse' })).toBeVisible()
    expect(screen.getByLabelText('Auswahl')).toHaveTextContent('bereich=wettbewerbe')
    expect(screen.getByLabelText('Auswahl')).toHaveTextContent('stat_jahr=2026')
    expect(screen.getByLabelText('Auswahl')).toHaveTextContent(`stat_wertung=${group.id}`)
    await waitFor(() => expect(calls.some((c) => c.key.endsWith('&membership=11'))).toBe(true))
  })

  it('fasst verschiedene Bedingungen nicht zu einem Durchschnitt zusammen', async () => {
    const other = {
      ...group,
      id: 'b'.repeat(24),
      label: 'LG 10 m · 5 Schuss · Ringe',
      counted_shots: 5,
    }
    fakeApi({
      [`GET ${base}`]: () => ({
        status: 200,
        body: {
          ...sample,
          selected_group: null,
          performance: null,
          groups: [group, other],
          group_summary: [
            { ...group, ...sample.performance },
            { ...other, ...sample.performance, average: 45 },
          ],
        },
      }),
    })
    render(
      <MemoryRouter>
        <CompetitionStatistics org={7} />
      </MemoryRouter>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Durchschnitt nach Wertungsbedingungen' }),
    ).toBeVisible()
    expect(
      screen.queryByRole('heading', { name: 'Durchschnittliche Ringe' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: group.label })).toBeVisible()
    expect(screen.getByRole('button', { name: other.label })).toBeVisible()
  })

  it('zeigt echte null und kennzeichnet fehlende Ergebnisse', async () => {
    fakeApi({
      'GET /api/orgs/7/competitions/member/11/statistics/': () => ({
        status: 200,
        body: {
          ...sample,
          performance: {
            ...sample.performance,
            average: 0,
            per_shot: 0,
            best: 0,
            change: null,
            previous_average: null,
          },
          results: [{ ...sample.results[0], value: null }],
        },
      }),
    })
    render(
      <MemoryRouter>
        <CompetitionStatistics org={7} membership={11} />
      </MemoryRouter>,
    )
    const tile = (await screen.findByRole('heading', { name: 'Durchschnittliche Ringe' })).closest(
      '.tile',
    )!
    expect(within(tile as HTMLElement).getByText('0 Ringe')).toBeVisible()
    expect(screen.getByText('Kein Ergebnis erfasst')).toBeVisible()
    expect(screen.getByText('Keine vergleichbaren Vorjahresergebnisse')).toBeVisible()
  })

  it('verwendet im Mitgliederbereich nur den persönlichen Zugang ohne Verwaltungslinks', async () => {
    const calls = fakeApi({
      'GET /api/portal/9/competition-statistics/': () => ({
        status: 200,
        body: { ...sample, members: [], member_options: undefined, can_open: false },
      }),
    })
    render(
      <MemoryRouter>
        <CompetitionStatistics accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Einzelergebnisse' })).toBeVisible()
    expect(screen.queryByRole('combobox', { name: 'Mitglied' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Herbstschießen' })).not.toBeInTheDocument()
    expect(calls.every((c) => !c.key.includes('/api/orgs/'))).toBe(true)
  })
})
