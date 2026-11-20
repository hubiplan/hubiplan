// Termine aus dem Mailprogramm: Bestätigungsseite einer Termineinladung an einen Verteiler
// (Daten erfunden).
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import type { PublicConfirm } from '../api/circulars.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedOut = () => ({ status: 401, body: { status: 401, data: { flows: [] } } })
const URL = '/api/public/circulars/confirm/tok/'

function renderAt(path: string) {
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

const waiting: PublicConfirm = {
  status: 'waiting',
  status_label: 'wartet auf Bestätigung',
  subject: 'Einladung: Sitzung',
  list: 'Mitglieder',
  address: 'alle@verein.example.org',
  organization: 'Schützenverein Musterstadt',
  body: '',
  attachments: [],
  counts: null,
  event: {
    action: 'new',
    title: 'Arbeitseinsatz am Vereinsheim',
    starts_at: '2099-03-07T09:00:00+01:00',
    ends_at: '2099-03-07T13:00:00+01:00',
    all_day: false,
    location: 'Vereinsheim',
    description: 'Bitte Handschuhe mitbringen.',
    video_url: '',
    repeat: '',
    attachments: ['Plan.pdf'],
    skipped: [],
    options: { rsvp_possible: true, rsvp: true, video_possible: true, video: false },
    visibility: 'members',
    event_url: '',
  },
}

describe('Termine aus dem Mailprogramm', () => {
  it('zeigt den Termin und übernimmt ihn mit den gewählten Einstellungen', async () => {
    const calls = fakeApi({
      [SESSION]: loggedOut,
      [`GET ${URL}`]: () => ({ status: 200, body: waiting }),
      [`POST ${URL}`]: () => ({
        status: 200,
        body: {
          ...waiting,
          status: 'sent',
          status_label: 'versendet',
          event: { ...waiting.event, options: null, event_url: 'https://h.example.org/termine' },
        },
      }),
    })
    renderAt('/rundschreiben/bestaetigen/tok')
    expect(await screen.findByText('Arbeitseinsatz am Vereinsheim')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Termin bestätigen' })).toBeInTheDocument()
    expect(screen.getByText('Sichtbar: Mitglieder (nicht öffentlich)')).toBeInTheDocument()
    expect(screen.getByText(/Plan\.pdf/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Neuen Videoraum (Nextcloud Talk) anlegen'))
    fireEvent.click(screen.getByLabelText('Zu- und Absagen anbieten'))
    fireEvent.click(screen.getByRole('button', { name: 'Übernehmen und informieren' }))
    expect(
      await screen.findByText(/Übernommen\. Der Verteiler wird informiert\./),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Termin in HUBIplan ansehen' })).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${URL}`)
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      action: 'send',
      rsvp: false,
      video: true,
    })
  })

  it('Absage: eigener Knopf, keine Einstellungen für Zu- und Absage', async () => {
    fakeApi({
      [SESSION]: loggedOut,
      [`GET ${URL}`]: () => ({
        status: 200,
        body: {
          ...waiting,
          event: {
            ...waiting.event,
            action: 'cancel',
            options: { rsvp_possible: false, rsvp: false, video_possible: false, video: false },
          },
        },
      }),
    })
    renderAt('/rundschreiben/bestaetigen/tok')
    expect(await screen.findByText('Absage')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Absage übernehmen' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Zu- und Absagen anbieten')).not.toBeInTheDocument()
  })
})
