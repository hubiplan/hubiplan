// Galerie der Webseite (Ralf 05.11.2026): Übersicht mit Unteralben, Album bearbeiten
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const base = '/api/orgs/7/website/'

const website = {
  state: 'public',
  effective_state: 'public',
  blocks: { gallery: false },
  public_key: 'abc',
  url: 'https://www.beispiel.test/',
  domains: [],
  preview_links: [],
  checks: [],
}
const site = {
  module_enabled: true,
  can_manage: true,
  can_edit_content: true,
  preview_only: false,
  block_labels: { gallery: 'Galerie' },
  units: [],
  website,
}

const album = (id: number, title: string, over: Record<string, unknown> = {}) => ({
  id,
  parent: null,
  title,
  slug: title.toLowerCase(),
  description: '',
  date: null,
  cover: null,
  published: true,
  show_captions: true,
  image_order: 'taken',
  children_order: 'date_desc',
  position: id,
  image_count: 0,
  updated_at: '2026-11-05T10:00:00Z',
  cover_url: null,
  ...over,
})

const listing = (albums: unknown[]) => ({
  albums,
  block_on: false,
  gallery_order: 'date_desc',
  image_orders: [
    { value: 'manual', label: 'eigene Reihenfolge' },
    { value: 'taken', label: 'Aufnahmedatum' },
  ],
  album_orders: [
    { value: 'manual', label: 'eigene Reihenfolge' },
    { value: 'date_desc', label: 'Datum, neueste zuerst' },
  ],
})

function renderApp(
  routes: Record<string, (body?: unknown) => { status: number; body?: unknown }>,
  path: string,
) {
  const org = testOrg({
    permissions: ['website.manage', 'website.content'],
    modules: ['website'],
  })
  const calls = fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${base}`]: () => ({ status: 200, body: site }),
    [`GET ${base}images/`]: () => ({ status: 200, body: [] }),
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
  return calls
}

describe('Webseite › Galerie', () => {
  it('zeigt Alben mit Unteralben und den Hinweis auf den ausgeschalteten Bereich', async () => {
    renderApp(
      {
        [`GET ${base}albums/`]: () => ({
          status: 200,
          body: listing([
            album(1, '2024', { image_count: 3, date: '2024-06-01' }),
            album(2, 'Schützenfest', { parent: 1, published: false }),
          ]),
        }),
      },
      '/webseite/galerie',
    )
    expect(
      await screen.findByText('Der Bereich „Galerie“ ist auf der Webseite noch ausgeschaltet.'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: /2024/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /Schützenfest/ })).toHaveTextContent(
      'nicht auf der Webseite',
    )
    expect(screen.getByLabelText('Alben sortieren nach')).toHaveValue('date_desc')
  })

  it('legt ein Album an und öffnet es zum Bearbeiten', async () => {
    const calls = renderApp(
      {
        [`GET ${base}albums/`]: () => ({ status: 200, body: listing([]) }),
        [`POST ${base}albums/`]: () => ({
          status: 201,
          body: { ...album(5, 'Königsball'), images: [] },
        }),
        [`GET ${base}albums/5/`]: () => ({
          status: 200,
          body: { ...album(5, 'Königsball'), images: [] },
        }),
        [`PUT ${base}albums/5/`]: () => ({
          status: 200,
          body: { ...album(5, 'Königsball', { published: false }), images: [] },
        }),
      },
      '/webseite/galerie',
    )
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Neues Album'), 'Königsball')
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    expect(await screen.findByLabelText('Titel')).toHaveValue('Königsball')
    expect(screen.getByText('Noch keine Bilder in diesem Album.')).toBeVisible()
    await user.click(screen.getByLabelText('Auf der Webseite zeigen'))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(calls.some((c) => c.key === `PUT ${base}albums/5/`)).toBe(true))
    const put = calls.find((c) => c.key === `PUT ${base}albums/5/`)
    expect(JSON.parse(String(put?.init?.body))).toMatchObject({ published: false })
  })
})
