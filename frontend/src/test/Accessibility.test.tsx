import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { DataTable } from '../components/DataTable.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { contrastRatio } from '../theme/contrast.ts'
import { buttonColors, hoverColor, linkColor, PAGE_BG } from '../theme/theme.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

describe('Farben aus dem Vereins-Theme', () => {
  it.each(['#ffffff', '#f5f6f4', '#f2f3f1', '#808080', '#ffd700', '#0e7c66', '#000000'])(
    '%s: Aktionsknöpfe unterscheiden sich vom Seitenhintergrund und behalten lesbare Schrift',
    (primary) => {
      const colors = buttonColors(primary, '#ffffff')
      for (const background of [colors.background, colors.hover]) {
        expect(contrastRatio(background, PAGE_BG)).toBeGreaterThanOrEqual(1.35)
        expect(contrastRatio(background, colors.foreground)).toBeGreaterThanOrEqual(4.5)
      }
    },
  )
  it('dunkelt helle Primärfarben für Links ab, bis 4,5 : 1 erreicht sind', () => {
    const link = linkColor('#909090')
    expect(contrastRatio(link, '#ffffff')).toBeGreaterThanOrEqual(4.5)
    // schon dunkle Farben bleiben unverändert
    expect(linkColor('#123e7a')).toBe('#123e7a')
  })

  it('wählt die Hoverfarbe so, dass dunkle Schrift lesbar bleibt', () => {
    const hover = hoverColor('#909090', '#1d2421')
    expect(contrastRatio(hover, '#1d2421')).toBeGreaterThan(contrastRatio('#909090', '#1d2421'))
    const dark = hoverColor('#123e7a', '#ffffff')
    expect(contrastRatio(dark, '#ffffff')).toBeGreaterThan(contrastRatio('#123e7a', '#ffffff'))
  })
})

describe('Tabellen auf dem Handy', () => {
  it('bietet die Sortierung zusätzlich als Auswahl an', async () => {
    render(
      <DataTable
        label="Züge"
        rows={[
          { id: 1, name: 'Herolde', count: 16 },
          { id: 2, name: 'Adler', count: 3 },
        ]}
        rowKey={(r) => r.id}
        columns={[
          { key: 'name', label: 'Name', value: (r) => r.name },
          { key: 'count', label: 'Mitglieder', value: (r) => r.count, numeric: true },
        ]}
        initialSort={{ key: 'name' }}
      />,
    )
    const cells = () =>
      screen
        .getAllByRole('row')
        .slice(1)
        .map((tr) => within(tr).getAllByRole('cell')[0].textContent)
    expect(cells()).toEqual(['Adler', 'Herolde'])
    expect(screen.getAllByRole('cell')[1]).toHaveAttribute('data-label', 'Mitglieder')
    await userEvent.setup().selectOptions(screen.getByLabelText('Sortieren nach'), 'count:desc')
    expect(cells()).toEqual(['Herolde', 'Adler'])
  })
})

describe('Navigation', () => {
  it('Menüknopf benennt seinen Zustand, Esc schließt und gibt den Fokus zurück', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [testOrg()] }),
    })
    render(
      <MemoryRouter initialEntries={['/einstellungen/xyz']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    const toggle = await screen.findByRole('button', { name: 'Navigation öffnen' })
    expect(toggle).toHaveAttribute('aria-controls', 'hauptnavigation')
    await user.click(toggle)
    expect(toggle).toHaveAccessibleName('Navigation schließen')
    expect(document.getElementById('inhalt')).toHaveAttribute('inert')
    await user.keyboard('{Escape}')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveFocus()
    expect(document.getElementById('inhalt')).not.toHaveAttribute('inert')
  })
})
