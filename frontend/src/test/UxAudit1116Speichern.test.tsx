// UX-Audit 16.11.2026, Punkt 16: ein Modell für Speichern, Verwerfen und Löschen
// (docs/ui-rueckmeldungen.md). VW-26: Dialoge schützen Eingaben von sich aus. VW-22/F-7: Farben
// gelten erst nach „Für alle übernehmen“.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { Modal } from '../components/Modal.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

describe('Dialoge schützen Eingaben (VW-26)', () => {
  function open(onClose: () => void, guard?: boolean) {
    render(
      <Modal title="Rolle besetzen" onClose={onClose} guard={guard}>
        <label>
          Notiz
          <input />
        </label>
      </Modal>,
    )
  }

  it('ohne Eingabe schließt Esc sofort', async () => {
    const onClose = vi.fn()
    open(onClose)
    await userEvent.setup().keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('nach einer Eingabe fragen Esc, „Schließen“ und der Klick daneben', async () => {
    const onClose = vi.fn()
    open(onClose)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Notiz'), 'Vertretung bis März')
    await user.keyboard('{Escape}')
    expect(await screen.findByText('Eingaben verwerfen?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Weiter bearbeiten' }))
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Notiz')).toHaveValue('Vertretung bis März')

    await user.click(screen.getByRole('button', { name: 'Schließen' }))
    await user.click(await screen.findByRole('button', { name: 'Weiter bearbeiten' }))
    expect(onClose).not.toHaveBeenCalled()

    await user.pointer({ keys: '[MouseLeft>]', target: document.querySelector('.modal-backdrop')! })
    await user.click(await screen.findByRole('button', { name: 'Verwerfen' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('guard={false}: ein Suchfeld schließt ohne Rückfrage', async () => {
    const onClose = vi.fn()
    open(onClose, false)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Notiz'), 'Suche')
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('Farben erst nach „Für alle übernehmen“ (VW-22, F-7)', () => {
  const theme = {
    primary_color: '#1f4e2c',
    accent_color: '',
    primary_color_name: 'Grün',
    accent_color_name: '',
    extra_colors: [],
    logo_url: null,
    effective: {
      primary: '#1f4e2c',
      on_primary: '#ffffff',
      accent: '#c9a227',
      on_accent: '#1d2421',
      logo_url: null,
      inherited_from: { colors: null, logo: null },
    },
  }

  it('ändert nichts ohne Knopf, verwirft auf Wunsch und übernimmt nur die Änderung', async () => {
    const org = testOrg({ permissions: ['org.edit', 'theme.edit'] })
    const calls = fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: { status: 200, data: { user: testUser } },
      }),
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
      'PATCH /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
    })
    const patches = () => calls.filter((c) => c.key === 'PATCH /api/orgs/7/theme/')
    render(
      <MemoryRouter initialEntries={['/einstellungen/erscheinungsbild']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    const name = await screen.findByLabelText('Name der Hauptfarbe', {}, { timeout: 5000 })
    const apply = screen.getByRole('button', { name: 'Für alle übernehmen' })
    expect(apply).toBeDisabled()

    await user.clear(name)
    await user.type(name, 'Tannengrün')
    expect(apply).toBeEnabled()
    expect(screen.getByText(/Bisher siehst nur du die Änderungen/)).toBeInTheDocument()
    // länger als das frühere automatische Speichern (700 ms)
    await new Promise((r) => setTimeout(r, 900))
    expect(patches()).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Änderungen verwerfen' }))
    expect(name).toHaveValue('Grün')
    expect(apply).toBeDisabled()

    await user.clear(name)
    await user.type(name, 'Waldgrün')
    await user.click(apply)
    await waitFor(() => expect(patches()).toHaveLength(1))
    expect(JSON.parse(String(patches()[0].init?.body))).toEqual({ primary_color_name: 'Waldgrün' })
    expect(
      await screen.findByText('Übernommen. Die Farben gelten jetzt für alle.'),
    ).toBeInTheDocument()
    expect(apply).toBeDisabled()
  })
})
