import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { entriesApi } from '../api/entries.ts'
import { financeApi } from '../api/finance.ts'
import { ApiError } from '../api/client.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

function setup(path: string) {
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [
        testOrg({
          modules: ['entries', 'finance'],
          permissions: ['entries.submit', 'finance.view', 'finance.edit'],
        }),
      ],
    }),
    'GET /api/orgs/7/entries/calls/': () => ({ status: 200, body: [] }),
    'GET /api/orgs/7/finance/accounts/': () => ({
      status: 200,
      body: [{ id: 1, kind: 'cash', is_active: true, name: 'Barkasse' }],
    }),
    'GET /api/orgs/7/finance/categories/': () => ({
      status: 200,
      body: [{ id: 2, kind: 'both', is_active: true, name: 'Auslagen' }],
    }),
    'GET /api/orgs/7/finance/cash-receipts/': () => ({
      status: 200,
      body: { count: 0, results: [], next: null, previous: null },
    }),
  })
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function warnsOnClose() {
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  return event.defaultPrevented
}

describe('Manuelle Entwürfe', () => {
  it('schließt eine unveränderte Ausschreibung ohne Rückfrage, schützt Änderungen und behält sie bei Abbruch', async () => {
    const user = userEvent.setup()
    setup('/meldungen')
    await user.click(await screen.findByRole('button', { name: 'Neue Ausschreibung erfassen' }))
    expect(warnsOnClose()).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Neue Ausschreibung erfassen' }))
    await user.type(screen.getByLabelText('Titel'), 'Vereinsturnier')
    expect(warnsOnClose()).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Weiter bearbeiten',
      }),
    )
    expect(screen.getByLabelText('Titel')).toHaveValue('Vereinsturnier')
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Verwerfen' }),
    )
    expect(screen.queryByLabelText('Titel')).not.toBeInTheDocument()
    expect(warnsOnClose()).toBe(false)
  })

  it('behält eine Ausschreibung nach Speicherfehler und entfernt die Warnung erst nach Erfolg', async () => {
    const user = userEvent.setup()
    setup('/meldungen')
    const create = vi
      .spyOn(entriesApi, 'create')
      .mockRejectedValueOnce(new ApiError(503, { detail: 'Bitte erneut versuchen.' }))
      .mockResolvedValueOnce({ id: 4 } as Awaited<ReturnType<typeof entriesApi.create>>)
    await user.click(await screen.findByRole('button', { name: 'Neue Ausschreibung erfassen' }))
    await user.type(screen.getByLabelText('Titel'), 'Vereinsturnier')
    await user.type(screen.getByLabelText('Veranstalter'), 'Musterverein')
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    await screen.findByText('Bitte erneut versuchen.')
    expect(warnsOnClose()).toBe(true)
    expect(screen.getByLabelText('Titel')).toHaveValue('Vereinsturnier')
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    await waitFor(() => expect(screen.queryByLabelText('Titel')).not.toBeInTheDocument())
    expect(create).toHaveBeenCalledTimes(2)
    expect(warnsOnClose()).toBe(false)
  })

  it('warnt für Quittungen nur bei eigenen Änderungen und schützt auch interne Navigationslinks', async () => {
    const user = userEvent.setup()
    setup('/finanzen/quittungen/neu')
    await screen.findByLabelText('Zweck')
    // Eine einzige Barkasse wird automatisch gewählt, ohne einen Entwurf zu erzeugen.
    expect(warnsOnClose()).toBe(false)
    await user.type(screen.getByLabelText('Zweck'), 'Material')
    expect(warnsOnClose()).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Weiter bearbeiten',
      }),
    )
    expect(screen.getByLabelText('Zweck')).toHaveValue('Material')
    await user.click(screen.getByRole('link', { name: 'Quittungen' }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Verwerfen' }),
    )
    await waitFor(() => expect(screen.queryByLabelText('Zweck')).not.toBeInTheDocument())
    expect(warnsOnClose()).toBe(false)
  })

  it('behält Quittungsangaben nach einem Serverfehler einschließlich Betrag', async () => {
    const user = userEvent.setup()
    setup('/finanzen/quittungen/neu')
    vi.spyOn(financeApi, 'createCashReceipt').mockRejectedValue(
      new ApiError(503, { detail: 'Nicht gespeichert.' }),
    )
    await user.type(await screen.findByLabelText('Empfänger (Name)'), 'Erika Muster')
    await user.type(screen.getByLabelText('Betrag in €'), '25,50')
    await user.type(screen.getByLabelText('Zweck'), 'Material')
    await user.selectOptions(screen.getByLabelText('Kategorie'), '2')
    await user.click(screen.getByRole('button', { name: 'Weiter zur Unterschrift' }))
    await screen.findByText('Nicht gespeichert.')
    expect(screen.getByLabelText('Betrag in €')).toHaveValue('25,50')
    expect(warnsOnClose()).toBe(true)
    // Rücksetzen aller selbst geänderten Werte stellt den ursprünglichen Zustand her.
    await user.clear(screen.getByLabelText('Empfänger (Name)'))
    await user.clear(screen.getByLabelText('Betrag in €'))
    await user.clear(screen.getByLabelText('Zweck'))
    await user.selectOptions(screen.getByLabelText('Kategorie'), '')
    await act(async () => {
      await Promise.resolve()
    })
    expect(warnsOnClose()).toBe(false)
  })
})
