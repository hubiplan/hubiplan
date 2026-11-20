import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalPinboard } from '../pages/portal/PortalPinboard.tsx'
import { fakeApi } from './fakeApi.ts'

const notice = (id: number, text: string, extra = {}) => ({
  id,
  text,
  unit: '',
  department: null,
  from: 'Musterverein',
  author: 'Erika Beispiel',
  pinned: false,
  visible_until: null,
  created_at: '2099-06-20T08:00:00Z',
  edited_at: null,
  push: false,
  pushed: false,
  expired: false,
  version: 1,
  can_edit: false,
  photos: [],
  new: false,
  ...extra,
})

describe('Pinnwand im Mitgliederbereich', () => {
  it('zeigt Beiträge mit „neu“ und Foto, ohne Formular für Leser', async () => {
    fakeApi({
      'GET /api/portal/9/pinboard/': () => ({
        status: 200,
        body: {
          notices: [
            notice(2, 'Bilder vom Sommerfest', {
              new: true,
              pinned: true,
              photos: [{ id: 5, url: '/api/portal/9/pinboard/2/photos/5/', width: 40, height: 30 }],
            }),
            notice(1, 'Der Bus fährt 10 Minuten später ab.'),
          ],
          targets: [],
          max_photos: 6,
          max_text: 2000,
        },
      }),
    })
    render(
      <MemoryRouter>
        <PortalPinboard accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Bilder vom Sommerfest')).toBeInTheDocument()
    expect(screen.getByText('neu')).toBeInTheDocument()
    expect(screen.getByText('angeheftet')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Foto 1 von 1' })).toHaveAttribute(
      'src',
      '/api/portal/9/pinboard/2/photos/5/',
    )
    expect(screen.queryByRole('heading', { name: 'Neuer Beitrag' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument()
  })

  it('schreibt mit Recht einen Beitrag an die Untereinheit', async () => {
    let sent: FormData | null = null
    const list = () => ({
      notices: sent ? [notice(3, String(sent.get('text')), { can_edit: true })] : [],
      targets: [
        { department: null, name: 'Musterverein' },
        { department: 4, name: 'Jägerzug' },
      ],
      max_photos: 6,
      max_text: 2000,
    })
    fakeApi({
      'GET /api/portal/9/pinboard/': () => ({ status: 200, body: list() }),
      'POST /api/portal/9/pinboard/': (init) => {
        sent = init?.body as FormData
        return { status: 201, body: notice(3, 'Treffpunkt Kirche', { push: true }) }
      },
    })
    render(
      <MemoryRouter>
        <PortalPinboard accessId={9} />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Neuer Beitrag' })
    await userEvent.selectOptions(screen.getByLabelText('An'), 'Jägerzug')
    await userEvent.type(screen.getByLabelText('Text'), 'Treffpunkt Kirche')
    await userEvent.click(screen.getByLabelText(/Push an die App senden/))
    await userEvent.click(screen.getByRole('button', { name: 'Veröffentlichen' }))
    expect(
      await screen.findByText('Beitrag veröffentlicht, Push geht an die App.'),
    ).toBeInTheDocument()
    expect(sent!.get('department')).toBe('4')
    expect(sent!.get('push')).toBe('1')
    expect(screen.getByRole('button', { name: 'Löschen' })).toBeInTheDocument()
  })
})
