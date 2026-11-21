import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Evaluation, PortalTraining as Data } from '../api/training.ts'
import { PortalTraining } from '../pages/portal/PortalTraining.tsx'
import { fakeApi } from './fakeApi.ts'

const months = Array.from({ length: 12 }, (_, i) => ({
  start: `2026-${String(i + 1).padStart(2, '0')}-01`,
  end: `2026-${String(i + 1).padStart(2, '0')}-28`,
  count: i === 3 ? 0 : 2,
}))

const evaluation: Evaluation = {
  on: '2026-11-20',
  start_12: '2025-11-21',
  start_24: '2024-11-21',
  member_since: '2020-03-01',
  acquisition: {
    ok: true,
    member_12_months: true,
    by_months: false,
    by_count: true,
    count: 22,
    needed: 18,
    months,
    longest_gap_days: 40,
    gap_ok: true,
    external: 2,
    internal: 20,
    mostly_own_club: true,
  },
  possession: [],
  pending: 0,
}

function data(extra: Partial<Data> = {}): Data {
  return {
    attendance: [
      {
        session: 5,
        date: '2026-11-18',
        title: 'Übungsabend Luftgewehr',
        kind: 'practice',
        kind_label: 'Übungsabend',
        department_name: '',
        source: 'code',
      },
    ],
    count_year: 14,
    count_12: 16,
    checkin: [],
    shooting_enabled: true,
    targets: [],
    shooting: { entries: [], evaluation, disciplines: [] },
    ...extra,
  }
}

describe('Training im Mitgliederbereich', () => {
  it('checkt mit dem Code aus dem QR-Link ein und zeigt die Anwesenheit', async () => {
    let checkedIn = false
    fakeApi({
      'GET /api/portal/9/training/': () => ({
        status: 200,
        body: data({
          checkin: checkedIn
            ? [
                {
                  id: 7,
                  date: '2026-11-20',
                  title: 'Training Sportpistole',
                  present: true,
                } as Data['checkin'][number],
              ]
            : [],
        }),
      }),
      'POST /api/portal/9/training/7/checkin/': (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ code: 'ABC123' })
        checkedIn = true
        return { status: 200, body: data() }
      },
    })
    render(<PortalTraining accessId={9} checkin={{ session: 7, code: 'ABC123' }} />)
    expect(
      await screen.findByText('Du bist eingecheckt. Viel Spaß beim Training!'),
    ).toBeInTheDocument()
    expect(await screen.findByText('eingecheckt')).toBeInTheDocument()
    expect(
      screen.getByText('Dieses Jahr 14-mal da, in den letzten 12 Monaten 16-mal.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Schießnachweis nach § 14 WaffG' })).toBeVisible()
  })

  it('meldet einen Schießtermin und kann ihn zurückziehen', async () => {
    const entry = {
      id: 31,
      membership: 4,
      date: '2026-11-15',
      discipline: 'Sportpistole',
      weapon_class: 'short' as const,
      weapon_class_label: 'Kurzwaffe',
      caliber: '.22 lr',
      permit_required: true,
      own_weapon: true,
      competition: false,
      place: 'Schießstand Beispielhausen',
      external: true,
      note: '',
      status: 'reported' as const,
      status_label: 'gemeldet',
      source: 'member' as const,
      source_label: 'vom Mitglied gemeldet',
      from_training: false,
      confirmed_by: '',
      confirmed_at: null,
    }
    fakeApi({
      'GET /api/portal/9/training/': () => ({ status: 200, body: data() }),
      'POST /api/portal/9/training/shooting/': (init) => {
        const body = JSON.parse(String(init?.body))
        expect(body.discipline).toBe('Sportpistole')
        expect(body.weapon_class).toBe('short')
        return {
          status: 200,
          body: data({ shooting: { entries: [entry], evaluation, disciplines: [] } }),
        }
      },
      'DELETE /api/portal/9/training/shooting/31/': () => ({ status: 200, body: data() }),
    })
    render(<PortalTraining accessId={9} />)
    await userEvent.type(await screen.findByLabelText('Disziplin'), 'Sportpistole')
    await userEvent.click(screen.getByRole('button', { name: 'Melden' }))
    expect(await screen.findByText('Gemeldet. Der Verein bestätigt den Termin.')).toBeVisible()
    expect(screen.getByText('gemeldet')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Zurückziehen' }))
    expect(await screen.findByText('Noch keine Einträge.')).toBeInTheDocument()
  })
})
