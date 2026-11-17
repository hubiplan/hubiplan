// UX-Audit 16.11.2026, kleine Web-Dinge: Einzeltasten-Kürzel „?“ abschaltbar (VW-03, WCAG 2.1.4),
// eigener Seitentitel für öffentliche Seiten und den Standmodus (VW-08, WCAG 2.4.2).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { setHelpShortcutEnabled } from '../help/shortcut.ts'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'

function renderAt(path: string, loggedIn = true) {
  fakeApi({
    [SESSION]: () =>
      loggedIn
        ? { status: 200, body: { status: 200, data: { user: testUser } } }
        : { status: 401, body: { status: 401 } },
    'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg({})] }),
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

afterEach(() => setHelpShortcutEnabled(true))

describe('Tastenkürzel „?“', () => {
  it('lässt sich unter Mein Konto abschalten', async () => {
    renderAt('/mein-konto')
    const user = userEvent.setup()
    const box = await screen.findByRole('checkbox', {
      name: /Taste „\?“ öffnet die Hilfe zu dieser Seite/,
    })
    expect(box).toBeChecked()
    await user.click(box)
    expect(box).not.toBeChecked()
    box.blur()
    await user.keyboard('?')
    expect(
      screen.queryByRole('complementary', { name: 'Hilfe zu dieser Seite' }),
    ).not.toBeInTheDocument()
    // wieder an: das Kürzel öffnet die Seitenhilfe
    await user.click(box)
    box.blur()
    await user.keyboard('?')
    expect(
      await screen.findByRole('complementary', { name: 'Hilfe zu dieser Seite' }),
    ).toBeInTheDocument()
  })
})

describe('Seitentitel öffentlicher Seiten', () => {
  it.each([
    ['/rueckmeldung/abc', 'Rückmeldung zum Termin'],
    ['/umfrage/abc', 'Umfrage'],
    ['/auslage/abc', 'Auslage einreichen'],
    ['/nachweis/abc', 'Nachweis einreichen'],
    ['/mitglied-werden/abc', 'Mitglied werden'],
    ['/mitglied-werden/stand/abc', 'Mitglied werden'],
    ['/antrag/abc', 'Stand des Antrags'],
    ['/rundschreiben/bestaetigen/abc', 'Empfang bestätigen'],
    ['/verbund/start', 'Anmeldung im Verbund'],
    ['/ki/verbinden', 'KI-Assistent verbinden'],
    ['/app/verbinden', 'App verbinden'],
    ['/stand/zugang/abc', 'Standmodus'],
  ])('%s heißt „%s“', async (path, title) => {
    renderAt(path, false)
    await waitFor(() => expect(document.title).toBe(`${title} · HUBIplan`))
  })
})
