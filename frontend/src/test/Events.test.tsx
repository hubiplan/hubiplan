import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { CalendarView } from '../components/calendar/CalendarView.tsx'
import { UpcomingTile } from '../components/calendar/UpcomingTile.tsx'
import {
  addDays,
  berlin,
  formatRange,
  monthGrid,
  monthStart,
  today,
} from '../components/calendar/time.ts'
import { occurrence } from './eventFixtures.ts'
import { fakeApi } from './fakeApi.ts'

const base = '/api/orgs/7/'
const day = (offset: number) => addDays(monthStart(today()), offset)

function listResponse(items: unknown[], canManage = true) {
  return {
    status: 200,
    body: {
      from: '',
      to: '',
      items,
      can_manage: canManage,
      categories: [{ id: 3, name: 'Versammlung', color: '#2f5f8f', is_active: true }],
    },
  }
}

function monthKey() {
  const grid = monthGrid(monthStart(today()))
  return `GET ${base}events/?from=${grid[0]}&to=${grid[grid.length - 1]}`
}

describe('Zeitrechnung', () => {
  it('rechnet in deutscher Zeit und zeigt Zeiträume lesbar', () => {
    expect(berlin('2026-03-29T00:30:00Z')).toEqual({ date: '2026-03-29', time: '01:30' })
    expect(berlin('2026-03-29T02:30:00Z')).toEqual({ date: '2026-03-29', time: '04:30' })
    expect(formatRange('2026-06-13T12:00:00Z', '2026-06-13T16:00:00Z', false)).toBe(
      'Sa 13.06.2026, 14:00 – 18:00 Uhr',
    )
    expect(formatRange('2026-08-28T22:00:00Z', '2026-08-31T22:00:00Z', true)).toBe(
      'Sa 29.08.2026 – Di 01.09.2026',
    )
    const grid = monthGrid('2026-06-01')
    expect(grid[0]).toBe('2026-06-01') // Montag
    expect(grid.length % 7).toBe(0)
  })
})

describe('Kalender', () => {
  it('zeigt Termine im Monat und öffnet die Details', async () => {
    const calls = fakeApi({
      [monthKey()]: () =>
        listResponse([
          occurrence(),
          occurrence({
            key: '2-x',
            event_id: 2,
            title: 'Schützenfest',
            all_day: true,
            visibility: 'public',
            owner: 'BSV',
            level: 'federation',
            can_edit: false,
            starts_at: `${day(12)}T00:00:00+01:00`,
            ends_at: `${day(14)}T00:00:00+01:00`,
          }),
        ]),
      [`GET ${base}events/1/`]: () => ({
        status: 200,
        body: {
          ...occurrence(),
          id: 1,
          description: 'Mit Neuwahlen.',
          hide_end_time: true,
          visibility_label: 'Mitglieder',
          repeat: 'none',
          repeat_label: 'einmalig',
          repeat_interval: 1,
          repeat_until: null,
          cancel_note: '',
          attachments: [
            {
              id: 5,
              name: 'Einladung.pdf',
              size: 2048,
              content_type: 'application/pdf',
              url: '/x',
            },
          ],
          exceptions: [],
          rsvp: {
            enabled: false,
            deadline: null,
            capacity: null,
            guests_allowed: false,
            max_guests: 10,
          },
        },
      }),
      [`PATCH ${base}events/1/`]: (init) => ({
        status: 200,
        body: {
          ...occurrence(),
          ...JSON.parse(String(init?.body)),
          id: 1,
          category: occurrence().category,
          attachments: [],
          exceptions: [],
          rsvp: { enabled: false },
        },
      }),
    })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Jahreshauptversammlung')).toBeInTheDocument()
    // mehrtägig: an drei Tagen
    expect(screen.getAllByText('Schützenfest')).toHaveLength(3)
    await userEvent.setup().click(screen.getByText('Jahreshauptversammlung'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Mit Neuwahlen.')).toBeInTheDocument()
    expect(within(dialog).getByText('Einladung.pdf')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Bearbeiten' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(within(dialog).getByRole('button', { name: 'Bearbeiten' }))
    const editForm = within(dialog).getByRole('form', { name: 'Termin' })
    const hideEnd = within(editForm).getByRole('checkbox', {
      name: 'Endzeit auf der Webseite ausblenden',
    })
    expect(hideEnd).toBeChecked()
    await user.click(hideEnd)
    await user.click(within(editForm).getByRole('button', { name: 'Schließen' }))
    const patch = calls.find((c) => c.key === `PATCH ${base}events/1/`)
    const body = JSON.parse(String(patch?.init?.body))
    expect(body.hide_end_time).toBe(false)
    const end = berlin(occurrence().ends_at)
    expect(body.ends_at).toBe(`${end.date}T${end.time}:00`)
  })

  it('öffnet einen Termin über den Direktlink', async () => {
    fakeApi({
      [monthKey()]: () => listResponse([occurrence()]),
      [`GET ${base}events/1/`]: () => ({
        status: 200,
        body: {
          ...occurrence(),
          id: 1,
          description: 'Mit Neuwahlen.',
          visibility_label: 'Mitglieder',
          repeat: 'none',
          repeat_label: 'einmalig',
          repeat_interval: 1,
          repeat_until: null,
          cancel_note: '',
          attachments: [],
          exceptions: [],
          rsvp: {
            enabled: false,
            deadline: null,
            capacity: null,
            guests_allowed: false,
            max_guests: 10,
          },
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={[`/termine?termin=1&datum=${today()}`]}>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Mit Neuwahlen.')).toBeInTheDocument()
  })

  it('legt für einen Termin eine Veranstaltungsabrechnung an', async () => {
    const detail = {
      ...occurrence(),
      id: 1,
      description: '',
      visibility_label: 'Mitglieder',
      repeat: 'none',
      repeat_label: 'einmalig',
      repeat_interval: 1,
      repeat_until: null,
      cancel_note: '',
      attachments: [],
      exceptions: [],
      rsvp: {
        enabled: false,
        deadline: null,
        capacity: null,
        guests_allowed: false,
        max_guests: 10,
      },
      project: null,
      can_link_project: true,
    }
    const calls = fakeApi({
      [monthKey()]: () => listResponse([occurrence()]),
      [`GET ${base}events/1/`]: () => ({ status: 200, body: detail }),
      [`POST ${base}events/1/project/`]: () => ({
        status: 200,
        body: { ...detail, project: { id: 4, name: 'Jahreshauptversammlung' } },
      }),
    })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.click(await screen.findByText('Jahreshauptversammlung'))
    const dialog = await screen.findByRole('dialog')
    await user.click(
      await within(dialog).findByRole('button', { name: 'Abrechnung für diesen Termin anlegen' }),
    )
    expect(
      await within(dialog).findByRole('link', { name: 'Jahreshauptversammlung' }),
    ).toHaveAttribute('href', '/finanzen/veranstaltungen/4')
    const post = calls.find((c) => c.key === `POST ${base}events/1/project/`)!
    expect(JSON.parse(String(post.init?.body))).toEqual({ create: true })
  })

  it('zeigt, was am Termin hängt: Versammlung, Dienstplan, Belegung', async () => {
    const detail = {
      ...occurrence(),
      id: 1,
      description: '',
      visibility_label: 'Mitglieder',
      repeat: 'none',
      repeat_label: 'einmalig',
      repeat_interval: 1,
      repeat_until: null,
      cancel_note: '',
      attachments: [],
      exceptions: [],
      rsvp: {
        enabled: false,
        deadline: null,
        capacity: null,
        guests_allowed: false,
        max_guests: 10,
      },
      meeting: { id: 5, status_label: 'in Vorbereitung' },
      helper_plans: [{ id: 8, title: 'Saaldienst', status_label: 'Entwurf' }],
      can_create_helper_plan: true,
      bookings: [{ id: 2, item: 'Schützenhaus', status_label: 'bestätigt' }],
    }
    fakeApi({
      [monthKey()]: () => listResponse([occurrence()]),
      [`GET ${base}events/1/`]: () => ({ status: 200, body: detail }),
    })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.click(await screen.findByText('Jahreshauptversammlung'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Zu diesem Termin')).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'Zur Versammlung' })).toHaveAttribute(
      'href',
      '/versammlungen?versammlung=5',
    )
    expect(within(dialog).getByRole('link', { name: 'Dienstplan: Saaldienst' })).toHaveAttribute(
      'href',
      '/helferdienste?plan=8',
    )
    expect(within(dialog).getByText('Belegt: Schützenhaus')).toBeInTheDocument()
    expect(
      within(dialog).getByRole('link', { name: 'Raum oder Gerät für diesen Termin buchen' }),
    ).toHaveAttribute('href', expect.stringContaining('/belegung?buchen=1&termin=1'))
  })

  it('legt einen Termin an', async () => {
    const user = userEvent.setup()
    const calls = fakeApi({
      [monthKey()]: () => listResponse([]),
      [`POST ${base}events/`]: () => ({ status: 201, body: { id: 9 } }),
    })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    await user.click(await screen.findByRole('button', { name: 'Neuer Termin' }))
    const dialog = await screen.findByRole('dialog', { name: 'Neuer Termin' })
    await user.type(within(dialog).getByLabelText('Titel'), 'Königsschießen')
    await user.selectOptions(within(dialog).getByLabelText(/Wer sieht den Termin/), 'public')
    const hideEnd = within(dialog).getByRole('checkbox', {
      name: 'Endzeit auf der Webseite ausblenden',
    })
    expect(hideEnd).not.toBeChecked()
    await user.click(hideEnd)
    await user.click(within(dialog).getByRole('button', { name: 'Termin anlegen' }))
    const post = calls.find((c) => c.key === `POST ${base}events/`)
    const body = JSON.parse(String(post?.init?.body))
    expect(body.title).toBe('Königsschießen')
    expect(body.visibility).toBe('public')
    expect(body.hide_end_time).toBe(true)
    expect(body.ends_at).toMatch(/T21:00:00$/)
    expect(body.starts_at).toMatch(/T19:00:00$/)
    expect(body.repeat).toBe('none')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('verwirft einen angefangenen Termin nicht per Esc und hält den Fokus im Dialog', async () => {
    const user = userEvent.setup()
    fakeApi({ [monthKey()]: () => listResponse([]) })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const opener = await screen.findByRole('button', { name: 'Neuer Termin' })
    await user.click(opener)
    const dialog = await screen.findByRole('dialog', { name: 'Neuer Termin' })
    // Ohne Eingaben schließt Esc sofort, der Fokus kehrt zum Auslöser zurück
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()

    await user.click(opener)
    const again = await screen.findByRole('dialog', { name: 'Neuer Termin' })
    expect(again).not.toBe(dialog)
    await user.type(within(again).getByLabelText('Titel'), 'Königsschießen')
    await user.keyboard('{Escape}')
    const ask = await screen.findByRole('alertdialog', { name: 'Entwurf verwerfen?' })
    await user.click(within(ask).getByRole('button', { name: 'Weiter bearbeiten' }))
    expect(within(again).getByLabelText('Titel')).toHaveValue('Königsschießen')

    // Tab läuft im Dialog im Kreis
    within(again).getByRole('button', { name: 'Abbrechen' }).focus()
    await user.tab()
    expect(again.contains(document.activeElement)).toBe(true)
  })

  it('nur lesen: kein Anlegen, kein Bearbeiten', async () => {
    fakeApi({
      [monthKey()]: () => listResponse([occurrence({ can_edit: false })], false),
    })
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <CalendarView base={base} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Jahreshauptversammlung')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neuer Termin' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Jahresprogramm/ })).toHaveAttribute(
      'href',
      `${base}events/program/?year=${today().slice(0, 4)}`,
    )
  })
})

describe('Terminaktion auf der Startseite', () => {
  function renderTile(calendar: string) {
    return render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <UpcomingTile base={calendar} />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
  }

  it.each(['/api/orgs/7/', '/api/depts/4/'])(
    'legt direkt im Kalender %s an und lädt die Kachel neu',
    async (calendar) => {
      let items: ReturnType<typeof occurrence>[] = []
      const list = `GET ${calendar}events/?from=${today()}&to=${addDays(today(), 90)}&upcoming=1`
      const calls = fakeApi({
        [list]: () => listResponse(items),
        [`POST ${calendar}events/`]: () => {
          items = [occurrence({ event_id: 9, title: 'Arbeitsabend' })]
          return { status: 201, body: { id: 9 } }
        },
      })
      renderTile(calendar)
      const user = userEvent.setup()
      await user.click(await screen.findByRole('button', { name: 'Neuer Termin' }))
      const dialog = await screen.findByRole('dialog', { name: 'Neuer Termin' })
      await user.type(within(dialog).getByLabelText('Titel'), 'Arbeitsabend')
      await user.selectOptions(within(dialog).getByLabelText('Kategorie'), '3')
      await user.click(within(dialog).getByRole('button', { name: 'Termin anlegen' }))
      expect(await screen.findByText('Arbeitsabend')).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      const post = calls.find((c) => c.key === `POST ${calendar}events/`)!
      expect(JSON.parse(String(post.init?.body))).toMatchObject({
        title: 'Arbeitsabend',
        category: 3,
      })
      expect(calls.filter((c) => c.key === list)).toHaveLength(2)
    },
  )

  it.each(['/api/orgs/7/', '/api/portal/2/'])(
    'bietet ohne Anlegerecht im Kalender %s nur die Übersicht an',
    async (calendar) => {
      fakeApi({
        [`GET ${calendar}events/?from=${today()}&to=${addDays(today(), 90)}&upcoming=1`]: () =>
          listResponse([], false),
      })
      renderTile(calendar)
      expect(await screen.findByText('In den nächsten Wochen keine Termine.')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Neuer Termin' })).not.toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Zum Kalender' })).toHaveAttribute('href', '/termine')
    },
  )
})
