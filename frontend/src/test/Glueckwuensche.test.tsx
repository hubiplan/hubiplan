// Rundschreiben › Glückwünsche: Entwürfe zeigen, versenden, auslassen, Einstellung speichern.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { GreetingsArea } from '../components/circulars/GreetingsArea.tsx'
import type { GreetingOverview } from '../api/greetings.ts'
import { fakeApi } from './fakeApi.ts'

const defaults = {
  birthday_subject: 'Herzlichen Glückwunsch zum Geburtstag',
  birthday_body: '{Anrede Du},\n\nalles Gute zum {Alter}. Geburtstag!',
  jubilee_subject: 'Herzlichen Glückwunsch zum Vereinsjubiläum',
  jubilee_body: '{Anrede Du},\n\nseit {Jubiläumsjahre} Jahren dabei!',
}

function overview(canEdit = true): GreetingOverview {
  return {
    settings: {
      birthdays: 'round',
      round_ages: '50, 60',
      every_year_from: 80,
      jubilees: false,
      approval: false,
      lead_days: 7,
      send_hour: 9,
      via_app: true,
      also_mail: false,
      reply_to: '',
      ...defaults,
      active: true,
      defaults,
    },
    batches: [
      {
        id: 5,
        date: '2000-01-01',
        kind: 'birthday',
        kind_label: 'Geburtstag',
        status: 'late',
        note: '',
        count: 2,
        circular: 41,
        letters_url: '/api/orgs/1/circulars/41/letters/',
        sent_at: null,
        recipients: [
          { name: 'Erika Muster', channel: 'letter', note: 'keine E-Mail-Adresse: Brief' },
          { name: 'Max Muster', channel: null, note: 'möchte keine Glückwünsche' },
        ],
        letters: 1,
      },
    ],
    upcoming: [
      {
        date: '2099-03-01',
        kind: 'birthday',
        member_id: 3,
        name: 'Paula Probe',
        age: 60,
        years: null,
        opted_out: false,
      },
    ],
    can_edit: canEdit,
  }
}

function show(canEdit = true) {
  const api = fakeApi({
    'GET /api/orgs/1/greetings/': () => ({ status: 200, body: overview(canEdit) }),
    'POST /api/orgs/1/greetings/5/skip/': () => ({ status: 200, body: { ok: true } }),
    'PUT /api/orgs/1/greetings/settings/': () => ({ status: 200, body: overview().settings }),
  })
  render(
    <MemoryRouter>
      <GreetingsArea orgId={1} />
    </MemoryRouter>,
  )
  return api
}

describe('Glückwünsche', () => {
  it('zeigt Entwurf mit Weg je Person, Brief-PDF und Vorschau', async () => {
    show()
    const draft = (await screen.findByText(/Erika Muster/)).closest('li.subcard') as HTMLElement
    expect(within(draft).getByText(/Max Muster: kein Glückwunsch/)).toBeInTheDocument()
    expect(within(draft).getByRole('link', { name: '1 Brief drucken (PDF)' })).toHaveAttribute(
      'href',
      '/api/orgs/1/circulars/41/letters/',
    )
    expect(within(draft).getByText('nicht versendet')).toBeInTheDocument()
    expect(screen.getByText('Paula Probe')).toBeInTheDocument()
    expect(screen.getByText('60. Geburtstag')).toBeInTheDocument()
  })

  it('lässt aus und speichert die Einstellung', async () => {
    const api = show()
    await userEvent.click(await screen.findByRole('button', { name: 'Auslassen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/1/greetings/5/skip/')).toBe(true),
    )
    await userEvent.selectOptions(screen.getByLabelText('Geburtstage'), 'all')
    await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => {
      const put = api.find((c) => c.key === 'PUT /api/orgs/1/greetings/settings/')
      expect(JSON.parse(String(put?.init?.body)).birthdays).toBe('all')
    })
  })

  it('ohne Schreibrecht nur lesen', async () => {
    show(false)
    await screen.findByText(/Erika Muster/)
    expect(screen.queryByRole('button', { name: 'Auslassen' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Speichern' })).toBeNull()
  })
})
