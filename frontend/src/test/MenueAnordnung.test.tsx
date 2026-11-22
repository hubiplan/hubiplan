// Menü frei anordnen (konzepte/menue-frei-anordnen.md): Regeln der Anordnung, Menü und Editor.
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { AREAS, modules } from '../modules.tsx'
import {
  areaOf,
  freeIcon,
  fromArrangement,
  iconOf,
  ICON_KEYS,
  toArrangement,
} from '../menuLayout.ts'
import { EXTRA_ICONS } from '../menuIcons.tsx'
import type { MenuLayout } from '../menuLayout.ts'
import { byMenu, fillAreas, placeOf } from '../help/menu.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

// Die Standardanordnung steht doppelt: im Frontend (modules.tsx) und für Prüfung und Apps im
// Backend. scripts/test.sh hängt das Backend ein (wie bei McpHilfe.test.ts).
const STANDARD_PATH = resolve(process.cwd(), '../backend/organizations/menu_standard.json')
const STANDARD = existsSync(STANDARD_PATH)
  ? (JSON.parse(readFileSync(STANDARD_PATH, 'utf-8')) as {
      areas: { id: string }[]
      items: Record<string, string>
      icons: string[]
    })
  : undefined

const WEBSITE_OWN: MenuLayout = {
  v: 1,
  areas: [
    { id: 'start' },
    { id: 'mitglieder' },
    { id: 'b1', label: 'Schießsport', label_en: 'Shooting', icon: 'wettbewerbe' },
    { id: 'webseite' },
    { id: 'finanzen' },
    { id: 'verein' },
  ],
  items: { geschaeftspartner: 'verein', termine: 'b1' },
}

function renderApp(path: string) {
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

describe('Anordnung des Menüs', () => {
  it.skipIf(!STANDARD)('Standard im Backend passt zu modules.tsx', () => {
    expect(STANDARD!.areas.map((a) => a.id)).toEqual(AREAS.map((a) => a.id))
    expect(STANDARD!.items).toEqual(Object.fromEntries(modules.map((m) => [m.id, m.area])))
    expect(STANDARD!.icons).toEqual(EXTRA_ICONS.map((x) => x.id))
  })

  it('kein Zeichen kommt doppelt vor', () => {
    const svg = (key: string) => renderToStaticMarkup(<>{iconOf(key)}</>)
    // Bereich und Menüpunkt mit derselben Kennung stehen nie zugleich in der Leiste
    const keys = ICON_KEYS
    expect(new Set(keys).size).toBe(keys.length)
    const seen = new Map<string, string>()
    const twice: string[] = []
    for (const key of keys) {
      const markup = svg(key)
      expect(markup, key).toContain('<path')
      const other = seen.get(markup)
      if (other) twice.push(`${other} = ${key}`)
      else seen.set(markup, key)
    }
    expect(twice).toEqual([])
  })

  it('ein neuer Hauptmenüpunkt bekommt ein freies Zeichen', () => {
    const areas = [{ id: 'start' }, { id: 'b1', label: 'A', icon: EXTRA_ICONS[0].id }]
    expect(freeIcon(areas)).toBe(EXTRA_ICONS[1].id)
  })

  it('ordnet jeden Menüpunkt genau einem vorhandenen Bereich zu', () => {
    const ids = WEBSITE_OWN.areas.map((a) => a.id)
    const byId = (id: string) => modules.find((m) => m.id === id)!
    expect(areaOf(WEBSITE_OWN, byId('webseite'))).toBe('webseite')
    expect(areaOf(WEBSITE_OWN, byId('termine'))).toBe('b1')
    expect(areaOf(WEBSITE_OWN, byId('geschaeftspartner'))).toBe('verein')
    // Bereich Planung fehlt: seine Menüpunkte stehen im ersten Bereich nach Start
    expect(areaOf(WEBSITE_OWN, byId('versammlungen'))).toBe('mitglieder')
    for (const m of modules) expect(ids, m.id).toContain(areaOf(WEBSITE_OWN, m))
    const arr = toArrangement(WEBSITE_OWN)
    const all = Object.values(arr.items).flat()
    expect(all.sort()).toEqual(modules.map((m) => m.id).sort())
  })

  it('speichert nur Abweichungen und den Standard als null', () => {
    expect(fromArrangement(toArrangement(null))).toBeNull()
    const back = fromArrangement(toArrangement(WEBSITE_OWN))!
    for (const m of modules) expect(areaOf(back, m), m.id).toBe(areaOf(WEBSITE_OWN, m))
    // Webseite steht von selbst in ihrem eigenen Bereich, Termine ausdrücklich in b1
    expect(back.items.webseite).toBeUndefined()
    expect(back.items.termine).toBe('b1')
  })

  it('die Hilfe folgt der Anordnung der Einheit', () => {
    const entry = { routes: ['/geschaeftspartner'], menu: undefined }
    expect(placeOf(entry)?.group).toBe('finanzen')
    expect(placeOf(entry, WEBSITE_OWN)?.group).toBe('verein')
    const sections = byMenu(
      [
        { ...entry, slug: 'x', title: 'x', kind: 'page', body: '', keywords: [], rights: [] },
      ] as never,
      WEBSITE_OWN,
    )
    expect(sections.map((s) => s.group)).toEqual(['verein'])
  })

  it('Platzhalter {bereich:…} nennt den Bereich nach der Anordnung', () => {
    expect(fillAreas('unter {bereich:belegung}')).toBe('unter Planung')
    expect(fillAreas('unter {bereich:termine}', WEBSITE_OWN)).toBe('unter Schießsport')
    expect(fillAreas('{bereich:gibtsnicht}')).toBe('{bereich:gibtsnicht}')
  })

  it('die Bereichsleiste zeigt die Anordnung der Einheit', async () => {
    const org = testOrg({
      modules: ['events', 'website', 'members'],
      permissions: ['events.view', 'website.view', 'members.view', 'org.edit'],
      menu_layout: WEBSITE_OWN,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/open-tasks/': () => ({ status: 200, body: { items: [] } }),
    })
    const { container } = renderApp('/bereich/b1')
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Schießsport' }),
    ).toBeInTheDocument()
    const rail = within(container.querySelector('.area-rail') as HTMLElement)
    const names = rail.getAllByRole('link').map((a) => a.textContent)
    expect(names).toContain('Schießsport')
    expect(names).toContain('Webseite')
    expect(names.indexOf('Schießsport')).toBeLessThan(names.indexOf('Webseite'))
  })

  it('der Editor verschiebt einen Menüpunkt und speichert die Abweichung', async () => {
    const org = testOrg({
      modules: ['events', 'members'],
      permissions: ['org.edit', 'events.view'],
    })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/menu-layout/': () => ({
        status: 200,
        body: { layout: null, can_undo: false, owned: true, max_areas: 12 },
      }),
      'PUT /api/orgs/7/menu-layout/': () => ({
        status: 200,
        body: {
          layout: { v: 1, areas: AREAS.map((a) => ({ id: a.id })), items: { termine: 'verein' } },
          can_undo: true,
          owned: true,
          max_areas: 12,
        },
      }),
    })
    renderApp('/einstellungen/menue')
    const move = await screen.findByRole('combobox', { name: '„Termine“ verschieben nach' })
    fireEvent.change(move, { target: { value: 'verein' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'PUT /api/orgs/7/menu-layout/')).toBe(true),
    )
    const put = calls.find((c) => c.key === 'PUT /api/orgs/7/menu-layout/')!
    const body = JSON.parse(String(put.init?.body)) as { layout: MenuLayout }
    expect(body.layout.items).toEqual({ termine: 'verein' })
    expect(await screen.findByText('Menü gespeichert.')).toBeInTheDocument()
  })
})
