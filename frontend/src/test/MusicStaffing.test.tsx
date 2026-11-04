import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { EnsembleTemplatesPage } from '../pages/music/EnsembleTemplatesPage.tsx'
import { StaffingPage } from '../pages/music/StaffingPage.tsx'
import { fakeApi } from './fakeApi.ts'

const context = vi.hoisted(() => ({ permissions: ['music.view', 'music.edit'] }))
vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, modules: ['music', 'events'], permissions: context.permissions }),
}))
beforeEach(() => {
  context.permissions = ['music.view', 'music.edit']
})

const base = '/api/orgs/7/music/'
const url = `${base}performances/9/staffing/`
function setup() {
  const calls = fakeApi({
    [`GET ${url}`]: () => ({
      status: 200,
      body: {
        title: 'Musterkonzert',
        cancelled: false,
        positions: [
          { id: 1, instrument: 'Tuba', register: '', required: 1, assigned: 0 },
          { id: 2, instrument: 'Flöte', register: '', required: 1, assigned: 0 },
        ],
        assignments: [],
        candidates: [
          { id: 11, name: 'Mika Beispiel', positions: [1] },
          { id: 12, name: 'Jo Beispiel', positions: [1, 2] },
        ],
      },
    }),
    [`GET ${base}ensemble-templates/`]: () => ({
      status: 200,
      body: [
        {
          id: 3,
          name: 'Kleine Besetzung',
          active: true,
          note: '',
          positions: [{ instrument: 'Tuba', register: '', required: 2 }],
        },
      ],
    }),
    [`POST ${url}`]: () => ({ status: 200, body: { created: 2, ok: true } }),
  })
  render(
    <MemoryRouter>
      <StaffingPage performance={9} />
    </MemoryRouter>,
  )
  return calls
}

it('legt eine wiederverwendbare Besetzungsvorlage mit Sollpositionen an', async () => {
  const calls = fakeApi({
    [`GET ${base}ensemble-templates/`]: () => ({ status: 200, body: [] }),
    [`POST ${base}ensemble-templates/`]: () => ({ status: 201, body: { id: 3 } }),
  })
  render(
    <MemoryRouter>
      <EnsembleTemplatesPage />
    </MemoryRouter>,
  )
  await userEvent.click(await screen.findByRole('button', { name: 'Vorlage anlegen' }))
  await userEvent.type(screen.getByLabelText('Name der Besetzungsvorlage'), 'Kleine Besetzung')
  await userEvent.type(screen.getByLabelText('Instrument'), 'Tuba')
  await userEvent.type(screen.getByLabelText('Register / Stimme'), '1')
  await userEvent.clear(screen.getByLabelText('Sollbesetzung'))
  await userEvent.type(screen.getByLabelText('Sollbesetzung'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await waitFor(() =>
    expect(calls.some((c) => c.key === `POST ${base}ensemble-templates/`)).toBe(true),
  )
  const request = calls.find((c) => c.key === `POST ${base}ensemble-templates/`)!
  expect(JSON.parse(String(request.init?.body))).toEqual({
    name: 'Kleine Besetzung',
    note: '',
    active: true,
    positions: [{ instrument: 'Tuba', register: '1', required: 2 }],
  })
  expect(new Headers(request.init?.headers).get('Idempotency-Key')).toBeTruthy()
})

it('zeigt eine Vorlage vor dem Anwenden und überträgt sie separat von der Einteilung', async () => {
  const calls = setup()
  await screen.findByRole('heading', { name: 'Besetzung planen' })
  expect(screen.getByText('Musterkonzert')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Besetzungsvorlage'), '3')
  expect(screen.getByText(/Tuba.*Sollbesetzung.*2/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Vorlage anwenden' }))
  await screen.findByText('Besetzungsvorlage angewendet.')
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body))).toEqual({
    action: 'apply_template',
    template: 3,
  })
})

it('ordnet Mehrinstrumentalisten nur einmal zu und verhindert eine übervolle Sammelauswahl', async () => {
  const calls = setup()
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Mika Beispiel' }))
  await userEvent.click(screen.getByRole('checkbox', { name: 'Jo Beispiel' }))
  expect(screen.getByRole('button', { name: 'Ausgewählte Musiker anfragen' })).toBeDisabled()
  await userEvent.selectOptions(screen.getByLabelText('Besetzungsposition für Jo Beispiel'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Ausgewählte Musiker anfragen' }))
  await screen.findByText('Ausgewählte Musiker wurden angefragt.')
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body))).toEqual({
    action: 'assign',
    assignments: [
      { musician: 11, position: 1 },
      { musician: 12, position: 2 },
    ],
  })
})

it('bietet einem Lesezugang keine Sammeländerungen an', async () => {
  context.permissions = ['music.view']
  setup()
  await screen.findByRole('heading', { name: 'Besetzung planen' })
  expect(screen.queryByRole('button', { name: 'Vorlage anwenden' })).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Ausgewählte Musiker anfragen' }),
  ).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox', { name: 'Mika Beispiel' })).not.toBeInTheDocument()
})
