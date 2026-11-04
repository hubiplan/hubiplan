import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client.ts'
import { devicesApi } from '../api/devices.ts'
import { entryResultsApi } from '../api/entryResults.ts'
import type { StandApi } from '../api/competitions.ts'
import { AppDevicesCard } from '../pages/settings/AppDevicesCard.tsx'
import { EntryResultsCard } from '../pages/entries/EntryResults.tsx'
import { LiveTables } from '../pages/competitions/LiveTables.tsx'
import { fakeApi } from './fakeApi.ts'

describe('Ladefehler gezielt wiederholen', () => {
  it('unterscheidet eine fehlgeschlagene Zugangsermittlung und Geräteliste von einer leeren Liste', async () => {
    fakeApi({})
    vi.spyOn(devicesApi, 'hasPortal')
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Zugang nicht ermittelbar.' }))
      .mockResolvedValue(true)
    vi.spyOn(devicesApi, 'list')
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Geräte nicht ermittelbar.' }))
      .mockResolvedValue([])
    const user = userEvent.setup()
    render(<AppDevicesCard />)
    await screen.findByText('Zugang nicht ermittelbar.')
    expect(screen.queryByText('Noch kein Gerät verbunden.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Erneut laden' }))
    await screen.findByText('Geräte nicht ermittelbar.')
    expect(screen.queryByText('Noch kein Gerät verbunden.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Erneut laden' }))
    await screen.findByText('Noch kein Gerät verbunden.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('hält nicht vorhandene Wettbewerbsergebnisse verborgen, zeigt echte Ladefehler aber mit Wiederholung', async () => {
    fakeApi({})
    const get = vi
      .spyOn(entryResultsApi, 'get')
      .mockRejectedValueOnce(new ApiError(404, { detail: 'Nicht vorhanden.' }))
    const empty = render(<EntryResultsCard org={7} call={4} />)
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    empty.unmount()
    get
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Ergebnisse nicht verfügbar.' }))
      .mockResolvedValueOnce({
        title: 'Turnier',
        date: '2026-06-12',
        status: 'live',
        status_label: 'läuft',
        final: false,
        share_ranking: false,
        prizes: [],
        scorings: [],
      })
    render(<EntryResultsCard org={7} call={4} />)
    await screen.findByText('Ergebnisse nicht verfügbar.')
    await userEvent.click(screen.getByRole('button', { name: 'Erneut laden' }))
    await screen.findByText(/Der Wettbewerb ist noch nicht abgeschlossen/)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('zeigt auch bei der ersten fehlgeschlagenen Live-Abfrage einen Wiederholungsweg', async () => {
    const standings = vi
      .fn<StandApi['standings']>()
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Live-Abfrage unterbrochen.' }))
      .mockResolvedValueOnce({
        scorings: [
          {
            scoring: 1,
            name: 'Einzelwertung',
            kind: 'einzel',
            rows: [],
            open: [],
            without_value: [],
          },
        ],
        open_shootoffs: 0,
      })
    const api = {
      standings,
      version: vi.fn().mockResolvedValue({ version: '1' }),
    } as unknown as StandApi
    render(<LiveTables api={api} />)
    await screen.findByText('Live-Abfrage unterbrochen.')
    await userEvent.click(screen.getByRole('button', { name: 'Erneut laden' }))
    await screen.findByRole('heading', { name: 'Einzelwertung' })
    expect(screen.getByText('Noch keine Werte.')).toBeInTheDocument()
    expect(standings).toHaveBeenCalledTimes(2)
  })
})
