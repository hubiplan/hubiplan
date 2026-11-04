import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { RehearsalProgramEditor } from '../pages/music/RehearsalProgramEditor.tsx'
import { OwnPracticePanel } from '../pages/music/OwnPractice.tsx'
import { fakeApi } from './fakeApi.ts'

const url = '/api/orgs/7/music/rehearsals/3/program/'
const original = '2026-12-01T18:00:00Z'
function setup() {
  const onSaved = vi.fn(async () => {}),
    onClose = vi.fn()
  const calls = fakeApi({
    [`GET ${url}?original_start=${encodeURIComponent(original)}`]: () => ({
      status: 200,
      body: {
        focus: 'Solo',
        overridden: true,
        is_series: true,
        items: [{ arrangement: 1, title: 'Altes Stück', focus: 'Takt 4' }],
        template: { focus: 'Rhythmus', items: [{ arrangement: 2, focus: 'Takt 1' }] },
      },
    }),
    [`POST ${url}`]: () => ({ status: 200, body: {} }),
  })
  render(
    <RehearsalProgramEditor
      url={url}
      originalStart={original}
      startsAt="2026-12-02T18:00:00Z"
      title="Musterprobe"
      arrangements={[
        { id: 1, name: 'Altes Stück' },
        { id: 2, name: 'Neues Stück' },
      ]}
      onSaved={onSaved}
      onClose={onClose}
    />,
  )
  return { calls, onSaved, onClose }
}

it('ändert Stücke und Schwerpunkt ausschließlich am ursprünglichen Einzeltermin', async () => {
  const { calls, onSaved } = setup()
  const focus = await screen.findByLabelText('Probenschwerpunkt')
  await userEvent.clear(focus)
  await userEvent.type(focus, 'Intonation')
  await userEvent.click(screen.getByRole('button', { name: 'Entfernen' }))
  await userEvent.click(screen.getByRole('button', { name: 'Probenstück hinzufügen' }))
  await userEvent.selectOptions(screen.getByLabelText('Arrangement'), '2')
  await userEvent.type(screen.getByLabelText('Schwerpunkt für dieses Stück'), 'Takt 12')
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body))).toEqual({
    original_start: original,
    scope: 'occurrence',
    focus: 'Intonation',
    items: [{ arrangement: 2, focus: 'Takt 12' }],
  })
})

it('lädt beim Wechsel zur gesamten Serie deren Vorlage statt des Einzelprogramms', async () => {
  const { calls, onSaved } = setup()
  await screen.findByLabelText('Änderungen gelten für')
  await userEvent.selectOptions(screen.getByLabelText('Änderungen gelten für'), 'series')
  expect(screen.getByLabelText('Probenschwerpunkt')).toHaveValue('Rhythmus')
  expect(screen.getByLabelText('Arrangement')).toHaveValue('2')
  expect(screen.getByText(/Termine mit eigenem Programm behalten ihre Inhalte/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body)).scope).toBe(
    'series',
  )
})

it('kann ein Einzelprogramm wieder auf die Serienvorlage zurücksetzen', async () => {
  const { calls, onSaved } = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Serienprogramm übernehmen' }))
  await userEvent.click(screen.getByRole('button', { name: 'Ja' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body)).scope).toBe(
    'inherit',
  )
})

it('zeigt im Musikerbereich das Programm und die Noten beim jeweiligen Termin', async () => {
  fakeApi({
    'GET /api/portal/9/music/practice/': () => ({
      status: 200,
      body: {
        scores: [],
        loans: [],
        rehearsals: [
          {
            id: 3,
            title: 'Erste Probe',
            original_start: original,
            starts_at: original,
            items: [{ title: 'Solostück', focus: 'Solo' }],
            overridden: true,
            scores: [{ id: 1, piece: 'Solostück', title: 'Tuba', url: '/solo/' }],
          },
          {
            id: 3,
            title: 'Zweite Probe',
            original_start: '2026-12-08T18:00:00Z',
            starts_at: '2026-12-08T18:00:00Z',
            items: [{ title: 'Marsch', focus: 'Rhythmus' }],
            scores: [{ id: 2, piece: 'Marsch', title: 'Tuba', url: '/marsch/' }],
          },
        ],
      },
    }),
  })
  render(<OwnPracticePanel accessId={9} />)
  const first = within((await screen.findByText(/Erste Probe/)).closest('article')!)
  const second = within(screen.getByText(/Zweite Probe/).closest('article')!)
  expect(first.getByRole('link', { name: 'Solostück · Tuba' })).toHaveAttribute('href', '/solo/')
  expect(first.queryByRole('link', { name: 'Marsch · Tuba' })).not.toBeInTheDocument()
  expect(second.getByRole('link', { name: 'Marsch · Tuba' })).toHaveAttribute('href', '/marsch/')
  expect(second.queryByText('Eigenes Programm für diesen Termin')).not.toBeInTheDocument()
})
