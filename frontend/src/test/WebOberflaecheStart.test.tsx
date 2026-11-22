import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

// Web-Oberfläche W10: Begrüßung mit Datum und Kurzübersicht „Zu erledigen“ auf der Startseite
const SESSION = 'GET /_allauth/browser/v1/auth/session'

function task(kind: string, label: string, title: string, link: string) {
  return { kind, kind_label: label, title, detail: '', created_at: null, link }
}

describe('Startseite der Verwaltung', () => {
  it('begrüßt mit Datum und fasst „Zu erledigen“ nach Art zusammen', async () => {
    const org = testOrg({ permissions: ['members.view', 'members.edit'] })
    fakeApi({
      [SESSION]: () => ({
        status: 200,
        body: { status: 200, data: { user: { ...testUser, display: 'Petra Erdacht' } } },
      }),
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/open-tasks/': () => ({
        status: 200,
        body: {
          items: [
            task('application', 'Mitgliedsantrag', 'Max Beispiel', '/mitglieder/anfragen'),
            task('application', 'Mitgliedsantrag', 'Eva Probe', '/mitglieder/anfragen'),
            task(
              'change_request',
              'Datenänderung',
              'Erika Muster',
              '/mitglieder/anfragen/aenderungen',
            ),
          ],
        },
      }),
      'GET /api/orgs/7/jubilees/?von=': () => ({ status: 200, body: [] }),
    })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText(/^(Guten Morgen|Guten Tag|Guten Abend), Petra$/)).toBeVisible()
    const summary = await screen.findByRole('list', { name: 'Kurzübersicht' })
    const links = within(summary).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['2 Mitgliedsantrag', '1 Datenänderung'])
    expect(links[1]).toHaveAttribute('href', '/mitglieder/anfragen/aenderungen')
  })
})
