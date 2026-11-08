// Schnelle Web-Korrekturen aus dem UI/UX-Audit vom 08.11.2026 (W-01, W-02, W-08, W-15, W-18)
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { Field } from '../components/ui.tsx'
import { watchFormValidation } from '../components/formValidation.ts'
import { splitLastWord } from '../learning/Aids.tsx'
import { settingsItems } from '../pages/settings/items.ts'
import { contrastRatio } from '../theme/contrast.ts'
import { blend, sidebarColor, sidebarMuted, SIDEBAR_TEXT, themeVars } from '../theme/theme.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

function renderApp(path: string, org: ReturnType<typeof testOrg>, routes = {}) {
  fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    ...routes,
  })
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// Rolle Kasse der Demodaten: Finanzen und Rechnungen, keine Einstellungen
const KASSE = ['finance.view', 'finance.edit', 'billing.view', 'billing.edit', 'members.view']

describe('W-01: Menüpunkte ohne Recht', () => {
  it('Kasse bekommt keine Einstellungen, der Vorstand alle lesbaren', () => {
    const kasse = testOrg({ permissions: KASSE }) as unknown as OrgSummary
    expect(settingsItems(kasse)).toEqual([])
    const board = testOrg({
      permissions: ['org.edit', 'theme.view', 'roles.manage'],
    }) as unknown as OrgSummary
    const labels = settingsItems(board).map((i) => i.label)
    expect(labels).toEqual(
      expect.arrayContaining([
        'Organisation',
        'Erscheinungsbild',
        'Impressum',
        'Rollen und Rechte',
      ]),
    )
    // Nur Farben ansehen: nur das Erscheinungsbild
    const theme = testOrg({ permissions: ['theme.view'] }) as unknown as OrgSummary
    expect(settingsItems(theme).map((i) => i.label)).toEqual(['Erscheinungsbild'])
  })

  it('Seitenleiste der Kasse zeigt „Einstellungen“ nicht und fragt keine Termine ab', async () => {
    const org = testOrg({
      permissions: KASSE,
      modules: ['members', 'finance', 'billing', 'events'],
    })
    renderApp('/', org)
    const nav = await screen.findByRole('navigation', { name: 'Module' })
    expect(await within(nav).findByRole('link', { name: 'Finanzen' })).toBeVisible()
    expect(within(nav).queryByRole('link', { name: 'Einstellungen' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Nächste Termine' })).toBeNull()
  })
})

describe('W-02: eigene Überschrift und eigener Seitentitel', () => {
  it('Finanzen › Beiträge & Rechnungen › Mahnungen heißt „Mahnungen“', async () => {
    const org = testOrg({
      permissions: KASSE,
      modules: ['members', 'finance', 'billing'],
      parent_name: null,
    })
    renderApp('/finanzen/rechnungen/mahnungen', org)
    expect(await screen.findByRole('heading', { level: 1, name: 'Mahnungen' })).toBeVisible()
    // Seit S-01 ist Mahnungen ein Eintrag der Gruppe „Beiträge & Rechnungen“
    // Pfad im Seitenkopf (S-05)
    const trail = screen.getByRole('navigation', { name: 'Pfad' })
    expect(
      within(trail)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Finanzen', 'Beiträge & Rechnungen', 'Mahnungen'])
    await waitFor(() =>
      expect(document.title).toMatch(/^Mahnungen · Beiträge & Rechnungen · Finanzen · /),
    )
  })

  it('Mitglieder › Einrichtung › Zusatzfelder heißt „Zusatzfelder“', async () => {
    const org = testOrg({ permissions: ['members.view', 'members.edit', 'org.edit'] })
    renderApp('/mitglieder/einrichtung/zusatzfelder', org)
    expect(await screen.findByRole('heading', { level: 1, name: 'Zusatzfelder' })).toBeVisible()
    await waitFor(() => expect(document.title).toMatch(/^Zusatzfelder · Einrichtung · Mitglieder/))
  })
})

describe('W-15: Kontrast der Seitenleiste', () => {
  const samples = [
    '#ffd500',
    '#7fdbff',
    '#ffc0cb',
    '#f0f0f0',
    '#ffffff',
    '#8b0000',
    '#14365d',
    '#37447c',
    '#0e7c66',
    '#f2b33d',
    '#c8a13a',
    '#e8b441',
    '#00ff00',
    '#ff6600',
    '#add8e6',
    '#ffe4e1',
    '#d3d3d3',
    '#000000',
    '#6a5acd',
    '#40e0d0',
  ]
  it.each(samples)('alle Texte der Seitenleiste bei %s mindestens 4,5 : 1', (primary) => {
    const vars = themeVars({ primary, on_primary: '#000000', accent: '#000000', on_accent: '#fff' })
    const bg = vars['--sidebar-bg']
    expect(bg).toBe(sidebarColor(primary))
    expect(contrastRatio(SIDEBAR_TEXT, bg)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(SIDEBAR_TEXT, blend('#ffffff', bg, 0.12))).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(vars['--sidebar-muted'], bg)).toBeGreaterThanOrEqual(4.5)
    expect(vars['--sidebar-muted']).toBe(sidebarMuted(bg))
  })

  it('dunkle Vereinsfarben behalten Seitenleiste und gedämpfte Schrift wie bisher', () => {
    // Musterstadt: unverändert 55 % abgedunkelt, 70 % Deckkraft
    expect(sidebarColor('#14365d')).toBe('#09182a')
    expect(sidebarMuted('#09182a')).toBe(blend(SIDEBAR_TEXT, '#09182a', 0.7))
  })
})

describe('W-18: „?“ an Begriffen bricht um', () => {
  it('nur das letzte Wort bleibt am „?“', () => {
    expect(splitLastWord('Davon überfällig')).toEqual(['Davon ', 'überfällig'])
    expect(splitLastWord('Beleg')).toEqual([null, 'Beleg'])
    expect(splitLastWord('Verantwortlich für den Inhalt')).toEqual([
      'Verantwortlich für den ',
      'Inhalt',
    ])
  })
})

describe('W-08: Pflichtfelder und Fehler am Feld', () => {
  beforeAll(() => watchFormValidation())

  function Form() {
    return (
      <form onSubmit={(e) => e.preventDefault()}>
        <Field label="Nachname" required />
        <label className="field">
          <span>Titel</span>
          <input required />
        </label>
        <button type="submit">Weiter</button>
      </form>
    )
  }

  it('zeigt bleibende Meldungen am Feld statt der Browserblase', () => {
    render(<Form />)
    const name = screen.getByLabelText('Nachname')
    const title = screen.getByLabelText('Titel')
    const invalid = new Event('invalid', { cancelable: true })
    name.dispatchEvent(invalid)
    title.dispatchEvent(new Event('invalid', { cancelable: true }))
    // Abgefangen: keine Blase des Browsers
    expect(invalid.defaultPrevented).toBe(true)
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(name).toHaveAccessibleDescription('Bitte fülle dieses Feld aus.')
    expect(title).toHaveAccessibleDescription('Bitte fülle dieses Feld aus.')
    expect(document.activeElement).toBe(name)

    // Nach der Eingabe verschwindet die Meldung
    fireEvent.change(name, { target: { value: 'Muster' } })
    fireEvent.input(name)
    expect(name).toHaveAttribute('aria-invalid', 'false')
    expect(screen.getAllByText('Bitte fülle dieses Feld aus.')).toHaveLength(1)
  })
})
