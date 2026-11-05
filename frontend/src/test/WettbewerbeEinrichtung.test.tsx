import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import {
  competitionsApi,
  type CompetitionDetail,
  type ShootingProgram,
  type TargetInfo,
} from '../api/competitions.ts'
import { ProgramsSetup } from '../pages/competitions/ProgramsSetup.tsx'
import { TargetPicker } from '../pages/competitions/TargetPicker.tsx'
import { fakeApi } from './fakeApi.ts'

const target = (key: string, name: string, group: string, diameter: number): TargetInfo => ({
  key,
  name,
  group,
  top_diameter: diameter,
  ring_width: 4.5,
  caliber: 4.5,
  top: 10,
  lowest: 1,
  inner_diameter: null,
  inner_mode: 'beruehren',
  black_diameter: 29,
  spots: 1,
  teiler_factor: 1,
  note: '',
  rings: [
    { ring: 1, diameter: 83 },
    { ring: 10, diameter },
  ],
  max_decimal: '10.7',
  distances: [10],
})
const lg = target('lg10_kyf', 'Luftgewehr 10 m Kyffhäuser', 'Luftgewehr', 2)
const kk = target('kk50', 'Kleinkaliber 50 m', 'Kleinkaliber', 10.4)
const lp = target('lp10', 'Luftpistole 10 m', 'Luftpistole', 11.5)
const catalog = {
  targets: [lg, lp, kk],
  custom: 'eigen',
  methods: [
    { value: 'frei', label: 'Wert frei eingeben' },
    { value: 'ringe', label: 'Ringe' },
  ],
  tie_breaks: [],
  presets: {},
  infrastructure_configured: true,
  recommended_targets: [lg.key],
}

beforeEach(() => competitionsApi.clearTargetCache(7))

it('zeigt passende Scheibenbilder und blendet den vollständigen Katalog auf Wunsch ein', async () => {
  const user = userEvent.setup(),
    onChange = vi.fn()
  render(
    <TargetPicker
      targets={[lg, lp, kk]}
      value={lg.key}
      customKey="eigen"
      onChange={onChange}
      recommendedTargets={[lg.key]}
      infrastructureConfigured
    />,
  )
  const choice = screen.getByRole('radio', { name: /Luftgewehr 10 m Kyffhäuser/ })
  expect(choice.closest('label')?.querySelector('svg')).not.toBeNull()
  expect(screen.queryByRole('radio', { name: /Kleinkaliber/ })).toBeNull()
  await user.click(
    screen.getByRole('button', { name: 'Alle Scheiben anzeigen (z. B. fremde Anlage)' }),
  )
  await user.click(screen.getByRole('radio', { name: /Kleinkaliber/ }))
  expect(onChange).toHaveBeenCalledWith('kk50')
})

it('behält eine bereits ausgewählte Scheibe außerhalb der Infrastruktur sichtbar', () => {
  render(
    <TargetPicker
      targets={[lg, kk]}
      value={kk.key}
      customKey="eigen"
      onChange={() => {}}
      recommendedTargets={[]}
      infrastructureConfigured
    />,
  )
  expect(screen.getByRole('radio', { name: /Kleinkaliber/ })).toBeChecked()
  expect(screen.queryByRole('radio', { name: /Luftgewehr/ })).toBeNull()
})

it('zeigt ohne Festlegung sämtliche Scheiben', () => {
  render(<TargetPicker targets={[lg, lp, kk]} value="" customKey="eigen" onChange={() => {}} />)
  expect(screen.getByRole('radio', { name: /Kleinkaliber/ })).toBeVisible()
  expect(screen.queryByRole('button', { name: /Alle Scheiben/ })).toBeNull()
})

const program: ShootingProgram = {
  id: 10,
  competition: 3,
  name: 'Vereinsschießen',
  sort_order: 1,
  target: lg.key,
  custom_target: {},
  shots: 5,
  position: '',
  distance: null,
  target_info: lg,
  has_results: false,
}
const competition = (hasResults = false) =>
  ({
    id: 3,
    own: true,
    form: 'rangliste',
    can_manage: true,
    status: 'vorbereitung',
    programs: [{ ...program, has_results: hasResults }],
    scorings: [{ id: 11, name: 'Einzelwertung', program: 10, kind: 'einzel' }],
  }) as unknown as CompetitionDetail

it('übernimmt die Disziplin aus der Bildauswahl und speichert gemeinsame Bedingungen erst zusammen', async () => {
  const reload = vi.fn(),
    user = userEvent.setup()
  const calls = fakeApi({
    'GET /api/orgs/7/competitions/targets/': () => ({ status: 200, body: catalog }),
    'PATCH /api/orgs/7/competitions/3/programs/10/': (init) => ({
      status: 200,
      body: { ...program, ...JSON.parse(String(init?.body)) },
    }),
  })
  render(
    <MemoryRouter>
      <ProgramsSetup org={7} comp={competition()} reload={reload} />
    </MemoryRouter>,
  )
  await user.click(await screen.findByRole('button', { name: /Alle Scheiben anzeigen/ }))
  await user.click(screen.getByRole('radio', { name: /Luftpistole 10 m/ }))
  expect(screen.getByText(/Luftpistole · 10 m · 4,5 mm/)).toBeVisible()
  expect(screen.queryByLabelText('Art')).toBeNull()
  const shots = screen.getByLabelText('Schüsse pro Person')
  await user.clear(shots)
  await user.type(shots, '6')
  expect(calls.filter((call) => call.key.startsWith('PATCH'))).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: 'Schießbedingungen übernehmen' }))
  await waitFor(() => expect(reload).toHaveBeenCalledOnce())
  expect(
    JSON.parse(String(calls.find((call) => call.key.startsWith('PATCH'))?.init?.body)),
  ).toMatchObject({ target: 'lp10', shots: 6, confirm_recalculation: false })
})

it('übernimmt abgebrochene Änderungen mit vorhandenen Ergebnissen nicht', async () => {
  const user = userEvent.setup()
  const calls = fakeApi({
    'GET /api/orgs/7/competitions/targets/': () => ({ status: 200, body: catalog }),
  })
  render(
    <MemoryRouter>
      <ProgramsSetup org={7} comp={competition(true)} reload={() => {}} />
    </MemoryRouter>,
  )
  const shots = await screen.findByLabelText('Schüsse pro Person')
  await user.clear(shots)
  await user.type(shots, '6')
  await user.click(screen.getByRole('button', { name: 'Schießbedingungen übernehmen' }))
  expect(await screen.findByRole('alertdialog')).toHaveTextContent(
    'Manuell eingegebene Summen bleiben erhalten',
  )
  await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
  expect(calls.filter((call) => call.key.startsWith('PATCH'))).toHaveLength(0)
  expect(shots).toHaveValue(6)
})

it('bestätigt zwischenzeitlich auf einem anderen Gerät erfasste Ergebnisse ohne Eingabeverlust', async () => {
  const user = userEvent.setup(),
    reload = vi.fn()
  let attempt = 0
  const calls = fakeApi({
    'GET /api/orgs/7/competitions/targets/': () => ({ status: 200, body: catalog }),
    'PATCH /api/orgs/7/competitions/3/programs/10/': () =>
      ++attempt === 1
        ? {
            status: 400,
            body: { confirm_recalculation: ['Inzwischen sind Ergebnisse vorhanden.'] },
          }
        : { status: 200, body: program },
  })
  render(
    <MemoryRouter>
      <ProgramsSetup org={7} comp={competition()} reload={reload} />
    </MemoryRouter>,
  )
  const shots = await screen.findByLabelText('Schüsse pro Person')
  await user.clear(shots)
  await user.type(shots, '6')
  await user.click(screen.getByRole('button', { name: 'Schießbedingungen übernehmen' }))
  await screen.findByRole('alert')
  expect(shots).toHaveValue(6)
  await user.click(screen.getByRole('button', { name: 'Schießbedingungen übernehmen' }))
  await screen.findByRole('alertdialog')
  await user.click(screen.getByRole('button', { name: 'Ändern und neu berechnen' }))
  await waitFor(() => expect(reload).toHaveBeenCalledOnce())
  const updates = calls.filter((call) => call.key.startsWith('PATCH'))
  expect(JSON.parse(String(updates[1]?.init?.body))).toMatchObject({
    shots: 6,
    confirm_recalculation: true,
  })
})

it('überträgt bei einer Umbenennung keine unveränderten Schießbedingungen', async () => {
  const user = userEvent.setup(),
    reload = vi.fn()
  const comp = competition(true)
  comp.programs!.push({ ...program, id: 20, name: 'Zweiter Durchgang' })
  const calls = fakeApi({
    'GET /api/orgs/7/competitions/targets/': () => ({ status: 200, body: catalog }),
    'PATCH /api/orgs/7/competitions/3/programs/10/': () => ({ status: 200, body: program }),
  })
  render(
    <MemoryRouter>
      <ProgramsSetup org={7} comp={comp} reload={reload} />
    </MemoryRouter>,
  )
  const names = await screen.findAllByLabelText('Bezeichnung des Durchgangs')
  await user.clear(names[0]!)
  await user.type(names[0]!, 'Neuer Name')
  await user.click(screen.getAllByRole('button', { name: 'Schießbedingungen übernehmen' })[0]!)
  await waitFor(() => expect(reload).toHaveBeenCalledOnce())
  const call = calls.find((entry) => entry.key.startsWith('PATCH'))
  expect(JSON.parse(String(call?.init?.body))).toEqual({
    name: 'Neuer Name',
    confirm_recalculation: false,
  })
})
