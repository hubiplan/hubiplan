import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { InstrumentsPage } from '../pages/music/InstrumentsPage.tsx'
import { InstrumentSelect } from '../pages/music/InstrumentSelect.tsx'
import { MusicTab } from '../pages/members/MusicTab.tsx'
import { fakeApi } from './fakeApi.ts'

// Instrumentenliste je Einheit (konzepte/instrumente.md); alles erfunden
vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, modules: ['music'], permissions: ['music.view', 'music.edit'] }),
}))

const base = '/api/orgs/7/music/'
const instruments = [
  { id: 1, name: 'Klarinette', group: 'wood', position: 1, active: true, used: 0 },
  { id: 2, name: 'Trompete', group: 'brass', position: 2, active: true, used: 3 },
  { id: 3, name: 'Flügelhorn', group: 'brass', position: 3, active: true, used: 0 },
  { id: 4, name: 'Harfe', group: 'other', position: 4, active: false, used: 0 },
]

it('zeigt die Liste nach Gruppen, sortiert um und entfernt nur Unbenutztes', async () => {
  const calls = fakeApi({
    [`GET ${base}instruments/`]: () => ({ status: 200, body: instruments }),
    [`POST ${base}instruments/order/`]: () => ({ status: 200, body: { ok: true } }),
  })
  render(
    <MemoryRouter>
      <InstrumentsPage />
    </MemoryRouter>,
  )
  const brass = await screen.findByRole('region', { name: 'Blech' })
  expect(within(brass).getByText('Trompete')).toBeInTheDocument()
  expect(within(brass).getByText(/3× verwendet/)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Weitere' })).toHaveTextContent('Ausgeblendet')
  // Verwendete Instrumente lassen sich nur ausblenden
  const trumpet = within(brass).getByText('Trompete').closest('li')!
  expect(within(trumpet).queryByRole('button', { name: 'Entfernen' })).not.toBeInTheDocument()
  expect(within(trumpet).getByRole('button', { name: 'Ausblenden' })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Flügelhorn nach oben' }))
  await waitFor(() =>
    expect(calls.some((c) => c.key === `POST ${base}instruments/order/`)).toBe(true),
  )
  const request = calls.find((c) => c.key === `POST ${base}instruments/order/`)!
  expect(JSON.parse(String(request.init?.body))).toEqual({ ids: [1, 3, 2, 4] })
})

it('wählt aus der Liste und erlaubt ein neues Instrument', async () => {
  const onChange = vi.fn()
  const { rerender } = render(
    <InstrumentSelect instruments={instruments} value="" onChange={onChange} label="Instrument" />,
  )
  const select = screen.getByRole('combobox', { name: 'Instrument' })
  // Ausgeblendete Instrumente stehen nicht zur Wahl
  expect(within(select).queryByRole('option', { name: 'Harfe' })).not.toBeInTheDocument()
  await userEvent.selectOptions(select, 'Trompete')
  expect(onChange).toHaveBeenLastCalledWith('Trompete')
  await userEvent.selectOptions(select, 'Neues Instrument …')
  rerender(
    <InstrumentSelect instruments={instruments} value="" onChange={onChange} label="Instrument" />,
  )
  await userEvent.type(screen.getByRole('textbox', { name: 'Instrument' }), 'A')
  expect(onChange).toHaveBeenLastCalledWith('A')
  // Ein ausgeblendetes Instrument bleibt an bestehenden Einträgen sichtbar
  cleanup()
  render(
    <InstrumentSelect instruments={instruments} value="Harfe" onChange={onChange} label="Alt" />,
  )
  expect(screen.getByRole('combobox', { name: 'Alt' })).toHaveValue('Harfe')
})

it('trägt in der Mitgliedsakte ein Instrument ein und legt das Musikerprofil an', async () => {
  const calls = fakeApi({
    [`GET ${base}musicians/`]: () => ({ status: 200, body: [] }),
    [`GET ${base}instruments/`]: () => ({ status: 200, body: instruments }),
    [`POST ${base}musicians/`]: () => ({
      status: 201,
      body: { id: 9, membership: 5, active: true },
    }),
    [`POST ${base}skills/`]: () => ({ status: 201, body: { id: 1 } }),
  })
  render(
    <MemoryRouter>
      <MusicTab orgId={7} memberId={5} />
    </MemoryRouter>,
  )
  await userEvent.click(await screen.findByRole('button', { name: 'Instrument hinzufügen' }))
  await userEvent.selectOptions(screen.getByLabelText('Instrument'), 'Trompete')
  await userEvent.type(screen.getByLabelText('Register / Stimme'), '1. Stimme')
  await userEvent.click(screen.getByRole('button', { name: 'Hinzufügen' }))
  await waitFor(() => expect(calls.some((c) => c.key === `POST ${base}skills/`)).toBe(true))
  const musician = calls.find((c) => c.key === `POST ${base}musicians/`)!
  expect(JSON.parse(String(musician.init?.body))).toEqual({ membership: 5, active: true })
  const skill = calls.find((c) => c.key === `POST ${base}skills/`)!
  expect(JSON.parse(String(skill.init?.body))).toEqual({
    musician: 9,
    instrument: 'Trompete',
    register: '1. Stimme',
    primary: true,
  })
})
