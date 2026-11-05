import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { CalendarView } from '../components/calendar/CalendarView.tsx'
import { formatDay, monthGrid } from '../components/calendar/time.ts'
import { setCatalogForTest } from '../i18n/index.ts'
import en from '../i18n/en.json'
import { fakeApi } from './fakeApi.ts'
import { occurrence } from './eventFixtures.ts'

const base = '/api/orgs/7/'
const grid = monthGrid('2026-11-01')
function show(items: ReturnType<typeof occurrence>[]) {
  fakeApi({
    [`GET ${base}events/?from=${grid[0]}&to=${grid.at(-1)}`]: () => ({
      status: 200,
      body: { items, can_manage: false, categories: [] },
    }),
  })
  return render(
    <MemoryRouter initialEntries={['/termine?datum=2026-11-01']}>
      <CalendarView base={base} />
    </MemoryRouter>,
  )
}

afterEach(() => setCatalogForTest('de'))

describe('Kalenderkontext', () => {
  it('unterscheidet gleichnamige Termine bereits sichtbar und im zugänglichen Namen', async () => {
    show([
      occurrence({
        title: 'Zugabend',
        owner: 'Erster Zug',
        starts_at: '2026-11-20T20:00:00+01:00',
        ends_at: '2026-11-20T22:00:00+01:00',
      }),
      occurrence({
        key: '2-x',
        event_id: 2,
        title: 'Zugabend',
        owner: 'Zweiter Zug',
        own: false,
        starts_at: '2026-11-20T20:00:00+01:00',
        ends_at: '2026-11-20T22:00:00+01:00',
      }),
    ])
    const first = await screen.findByRole('button', { name: /Zugabend · Erster Zug/ })
    const second = screen.getByRole('button', { name: /Zugabend · Zweiter Zug/ })
    expect(within(first).getByText('Erster Zug')).toBeInTheDocument()
    expect(within(second).getByText('Zweiter Zug')).toBeInTheDocument()
    expect(first).toHaveAccessibleName(/20:00 – 22:00 Uhr/)
  })

  it.each(['de', 'en'] as const)(
    'zeigt Beginn, Zwischentag und Ende tageweise (%s)',
    async (language) => {
      setCatalogForTest(language, en)
      show([
        occurrence({
          title: 'Wochenende',
          starts_at: '2026-11-20T23:05:00+01:00',
          ends_at: '2026-11-22T01:05:00+01:00',
        }),
      ])
      await screen.findAllByText('Wochenende')
      const start = within(screen.getByRole('group', { name: formatDay('2026-11-20') }))
      const middle = within(screen.getByRole('group', { name: formatDay('2026-11-21') }))
      const end = within(screen.getByRole('group', { name: formatDay('2026-11-22') }))
      expect(start.getByText('23:05')).toBeInTheDocument()
      expect(middle.getByText(language === 'en' ? 'Continued' : 'Fortsetzung')).toBeInTheDocument()
      expect(
        end.getByText(language === 'en' ? 'Continued until 01:05' : 'Fortsetzung bis 01:05'),
      ).toBeInTheDocument()
      expect(end.queryByText('23:05')).not.toBeInTheDocument()
      expect(end.getByRole('button')).toHaveAccessibleName(
        language === 'en'
          ? /20\/11\/2026, 23:05.*22\/11\/2026, 01:05/
          : /20\.11\.2026, 23:05.*22\.11\.2026, 01:05/,
      )
    },
  )

  it('zeigt ein Ende um Mitternacht am Vortag und keinen zusätzlichen Tagesabschnitt', async () => {
    show([
      occurrence({
        title: 'Lager',
        starts_at: '2026-11-20T12:00:00+01:00',
        ends_at: '2026-11-22T00:00:00+01:00',
      }),
    ])
    await screen.findAllByText('Lager')
    expect(
      within(screen.getByRole('group', { name: formatDay('2026-11-21') })).getByText(
        'Fortsetzung bis 24:00',
      ),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole('group', { name: formatDay('2026-11-22') })).queryByRole('button'),
    ).not.toBeInTheDocument()
  })

  it('erhält Ganztägigkeit, Absage und Kalenderquelle auch ohne Uhrzeit', async () => {
    setCatalogForTest('en', en)
    show([
      occurrence({
        title: 'Festival',
        all_day: true,
        is_cancelled: true,
        source: 'Partnerkalender',
        starts_at: '2026-11-20T00:00:00+01:00',
        ends_at: '2026-11-21T00:00:00+01:00',
      }),
    ])
    const entries = await screen.findAllByRole('button', {
      name: /Festival.*Partnerkalender.*cancelled/,
    })
    expect(entries).toHaveLength(2)
    expect(within(entries[1]).getByText('Continued · all day')).toBeInTheDocument()
    expect(entries[1]).not.toHaveAccessibleName(/00:00/)
  })

  it('zeigt in der mobilen Standardansicht vollständigen Zeitraum und Kalenderkontext', async () => {
    // Die Listenansicht ist auf kleinen Bildschirmen Standard; hier unabhängig von matchMedia.
    localStorage.setItem('hubiplan.kalenderansicht', 'list')
    fakeApi({
      [`GET ${base}events/?from=2026-11-01&to=2027-10-31`]: () => ({
        status: 200,
        body: {
          items: [
            occurrence({
              title: 'Nachtwache',
              owner: 'Erster Zug',
              starts_at: '2026-11-20T23:05:00+01:00',
              ends_at: '2026-11-21T01:05:00+01:00',
            }),
          ],
          can_manage: false,
          categories: [],
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/termine?datum=2026-11-01']}>
        <CalendarView base={base} />
      </MemoryRouter>,
    )
    const entry = await screen.findByRole('button', { name: /Nachtwache/ })
    expect(entry).toHaveAccessibleName(/20\.11\.2026, 23:05 Uhr.*21\.11\.2026, 01:05 Uhr/)
    expect(within(entry).getByText(/Erster Zug/)).toBeInTheDocument()
  })
})
