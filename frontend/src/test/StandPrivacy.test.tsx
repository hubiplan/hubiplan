import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ApiError } from '../api/client.ts'
import { orgStandApi, tokenStandApi } from '../api/competitions.ts'
import {
  authorizeStandCache,
  bindStandUser,
  clearStandCache,
  loadStandCache,
  pendingStandInputs,
  removeLegacyStandCache,
  saveStandCache,
  standRevision,
  standTokenKey,
  standUser,
} from '../api/standCache.ts'
import { AuthProvider, useAuth } from '../auth/AuthContext.tsx'
import { StandTokenPage } from '../pages/competitions/StandPage.tsx'
import { useStandStore } from '../pages/competitions/standStore.ts'
import { fakeApi, testUser } from './fakeApi.ts'

vi.mock('../pages/competitions/StandPanel.tsx', () => ({ StandPanel: () => null }))
vi.mock('../pages/competitions/LiveTables.tsx', () => ({ LiveTables: () => null }))
vi.mock('../pages/competitions/BirdStand.tsx', () => ({ BirdStand: () => null }))
vi.mock('../pages/competitions/BirdSetup.tsx', () => ({ StandAccessCard: () => null }))

const local = {
  starters: [],
  members: [{ membership: 123, name: 'Synthetische Testperson' }],
  ops: [],
  recent: [],
  savedAt: null,
}
const detail = {
  id: 42,
  title: 'Privater Testwettbewerb',
  own: true,
  form: 'einzel',
  stand_access: { expires_at: '2099-01-01T00:00:00Z', label: 'Test' },
}
beforeEach(() => {
  clearStandCache()
  bindStandUser(null)
})

it('entfernt auch beschädigte und ungebundene Altbestände', () => {
  localStorage.setItem('hubiplan.stand.detail.alt', '{"name":"Private Testdaten"')
  localStorage.setItem('hubiplan.stand.7.42', JSON.stringify({ ...local, ops: [{ op: 'score' }] }))
  expect(removeLegacyStandCache()).toBe(1)
  expect(localStorage.getItem('hubiplan.stand.detail.alt')).toBeNull()
  expect(localStorage.getItem('hubiplan.stand.7.42')).toBeNull()
})

it('legt keinen vollständigen Standschlüssel in den Metadaten der Service-Worker-Schale ab', async () => {
  const handlers: Record<string, (event: unknown) => void> = {}
  const stored: Response[] = []
  const response = new Response('<html>Statische Schale</html>')
  Object.defineProperty(response, 'url', {
    value: 'https://example.invalid/stand/zugang/privater-schluessel',
  })
  runInNewContext(readFileSync('public/sw-stand.js', 'utf8'), {
    self: {
      addEventListener: (type: string, handler: (event: unknown) => void) => {
        handlers[type] = handler
      },
    },
    Response,
    fetch: async () => response,
    caches: {
      open: async () => ({
        put: async (_key: string, value: Response) => {
          stored.push(value)
        },
      }),
    },
  })
  let done!: Promise<void>
  handlers.message({
    data: { type: 'merken', page: '/stand/zugang/privater-schluessel', assets: [] },
    waitUntil: (promise: Promise<void>) => {
      done = promise
    },
  })
  await done
  expect(stored).toHaveLength(1)
  expect(stored[0].url).toBe('')
  expect(await stored[0].text()).toBe('<html>Statische Schale</html>')
})

function Account() {
  const { user, logout, setUser } = useAuth()
  return (
    <>
      <p>{user?.email ?? 'abgemeldet'}</p>
      <button onClick={() => void logout()}>Abmelden</button>
      <button onClick={() => setUser({ ...testUser, id: 999 })}>Kontowechsel</button>
    </>
  )
}

it('entfernt bei bestätigter Abmeldung Konto- und Token-Caches', async () => {
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { data: { user: testUser } },
    }),
    'DELETE /_allauth/browser/v1/auth/session': () => ({ status: 401 }),
  })
  render(
    <AuthProvider>
      <Account />
    </AuthProvider>,
  )
  await screen.findByText(testUser.email)
  const scope = orgStandApi(7, 42).key
  authorizeStandCache(scope)
  saveStandCache(scope, 'local', local, standRevision())
  authorizeStandCache('token.test')
  saveStandCache('token.test', 'local', local, standRevision())
  await userEvent.click(screen.getByRole('button', { name: 'Abmelden' }))
  await screen.findByText('abgemeldet')
  expect(loadStandCache(scope, 'local')).toBeNull()
  expect(loadStandCache('token.test', 'local')).toBeNull()
  expect(localStorage.getItem('hubiplan.stand.user')).toBeNull()
})

it('fragt vor dem Verlust ungesendeter Eingaben und lässt Abbrechen zu', async () => {
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { data: { user: testUser } },
    }),
  })
  render(
    <AuthProvider>
      <Account />
    </AuthProvider>,
  )
  await screen.findByText(testUser.email)
  const scope = orgStandApi(7, 42).key
  authorizeStandCache(scope)
  saveStandCache(scope, 'local', { ...local, ops: [{ op: 'score' }] }, standRevision())
  await userEvent.click(screen.getByRole('button', { name: 'Abmelden' }))
  expect(await screen.findByRole('alertdialog')).toHaveTextContent('1 Stand-Eingaben')
  await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
  expect(loadStandCache(scope, 'local')).not.toBeNull()
  expect(calls.some((c) => c.key.startsWith('DELETE '))).toBe(false)
})

it('behält Konto und Cache, wenn der Server die Abmeldung nicht bestätigt', async () => {
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { data: { user: testUser } },
    }),
    'DELETE /_allauth/browser/v1/auth/session': () => ({ status: 503 }),
  })
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
  await waitFor(() => expect(result.current.user?.id).toBe(testUser.id))
  const scope = orgStandApi(7, 42).key
  authorizeStandCache(scope)
  saveStandCache(scope, 'local', local, standRevision())
  await act(async () => {
    await expect(result.current.logout()).rejects.toBeInstanceOf(ApiError)
  })
  expect(result.current.user?.id).toBe(testUser.id)
  expect(loadStandCache(scope, 'local')).not.toBeNull()
})

it.each([429, 500, 502, 503])(
  'behält offene Eingaben bei ungewissem Sessionstart %s und sperrt die Oberfläche',
  async (status) => {
    bindStandUser(testUser.id)
    const scope = orgStandApi(7, 42).key
    authorizeStandCache(scope)
    saveStandCache(scope, 'local', { ...local, ops: [{ op: 'starter' }] }, standRevision())
    fakeApi({ 'GET /_allauth/browser/v1/auth/session': () => ({ status }) })
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(result.current.offline).toBe(false)
    expect(loadStandCache(scope, 'local')).not.toBeNull()
    expect(pendingStandInputs()).toBe(1)
  },
)

it.each([401, 403])('entfernt Konto-Cache bei bestätigter Sessionablehnung %s', async (status) => {
  bindStandUser(testUser.id)
  const scope = orgStandApi(7, 42).key
  authorizeStandCache(scope)
  saveStandCache(scope, 'local', local, standRevision())
  fakeApi({ 'GET /_allauth/browser/v1/auth/session': () => ({ status }) })
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(loadStandCache(scope, 'local')).toBeNull()
})

it.each([
  'photo',
  'finish',
  'list',
  'create',
  'update',
  'updateEntry',
  'unitMembers',
  'remove',
] as const)('beendet Offlinezugriff auch nach 403 bei %s', async (action) => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  authorizeStandCache(api.key)
  saveStandCache(api.key, 'local', local, standRevision())
  document.cookie = 'csrftoken=test'
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 403 }))
  const actions = {
    photo: () => api.photo(1, new Blob(['test'], { type: 'image/png' })),
    finish: () => api.finish!(),
    list: () => api.shootoffs.list(),
    create: () => api.shootoffs.create(1, ['starter'], {}),
    update: () => api.shootoffs.update(1, {}),
    updateEntry: () => api.shootoffs.updateEntry(1, { value: '1' }),
    unitMembers: () => api.shootoffs.unitMembers(1),
    remove: () => api.shootoffs.remove!(1),
  }
  await expect(actions[action]()).rejects.toBeInstanceOf(ApiError)
  expect(loadStandCache(api.key, 'local')).toBeNull()
})

it('behandelt einen einzelnen fehlenden Stech-Eintrag nicht als Entzug des ganzen Standes', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  authorizeStandCache(api.key)
  saveStandCache(api.key, 'local', local, standRevision())
  document.cookie = 'csrftoken=test'
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 404 }))
  await expect(api.shootoffs.updateEntry(99, { value: '1' })).rejects.toBeInstanceOf(ApiError)
  expect(loadStandCache(api.key, 'local')).not.toBeNull()
})

it('verwirft auch verspätete Fotoantworten nach dem Kontowechsel', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  document.cookie = 'csrftoken=test'
  let finish!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  const pending = api.photo(1, new Blob(['test'], { type: 'image/png' }))
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  bindStandUser(2)
  finish(new Response('{}', { status: 200 }))
  await expect(pending).rejects.toBeInstanceOf(ApiError)
})

it('schreibt eine vor Abmeldung gestartete Mitgliederantwort nicht zurück', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  let finish!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    if (String(url).endsWith('/members/'))
      return new Promise((resolve) => {
        finish = resolve
      })
    return new Response(JSON.stringify(String(url).endsWith('/starters/') ? [] : detail), {
      status: 200,
    })
  })
  const { result } = renderHook(() => useStandStore(api, () => 'Test'))
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  await act(async () => {
    clearStandCache()
    bindStandUser(null)
    finish(new Response(JSON.stringify(local.members), { status: 200 }))
  })
  expect(result.current.local.members).toEqual([])
  expect(loadStandCache(api.key, 'local')).toBeNull()
})

it('zählt auch ungesendete Eingaben bei vollem Browserspeicher für die Abmeldewarnung', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  fakeApi({
    'GET /api/orgs/7/competitions/42/': () => ({ status: 200, body: detail }),
    'GET /api/orgs/7/competitions/42/starters/': () => ({ status: 200, body: [] }),
    'GET /api/orgs/7/competitions/42/members/': () => ({ status: 200, body: local.members }),
    'POST /api/orgs/7/competitions/42/sync/': () => ({ status: 503 }),
  })
  const { result } = renderHook(() => useStandStore(api, () => 'Test'))
  await waitFor(() => expect(result.current.local.members).toHaveLength(1))
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new DOMException('quota', 'QuotaExceededError')
  })
  act(() => result.current.push({ op: 'starter', client_key: 'test', name: 'Test' }))
  await waitFor(() => expect(pendingStandInputs()).toBe(1))
  expect(result.current.syncError).toContain('nur im Arbeitsspeicher')
})

it('gibt dem nächsten Konto keine Daten und verwirft verspätete Antworten', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  authorizeStandCache(api.key)
  saveStandCache(api.key, 'local', local, standRevision())
  let finish!: (response: Response) => void
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  const pending = api.get()
  bindStandUser(2)
  finish(new Response(JSON.stringify(detail), { status: 200 }))
  await expect(pending).rejects.toBeInstanceOf(ApiError)
  expect(loadStandCache(api.key, 'local')).toBeNull()
  expect(orgStandApi(7, 42).key).not.toBe(api.key)
})

it.each([401, 403, 404])(
  'zeigt bei Serverablehnung %s keine Token-Detaildaten aus dem Cache',
  async (status) => {
    const token = 'abcdefghijkl-test-full-credential'
    const key = await standTokenKey(token)
    authorizeStandCache(key, detail.stand_access.expires_at)
    saveStandCache(key, 'detail', detail, standRevision())
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status }))
    render(
      <MemoryRouter initialEntries={[`/stand/zugang/${token}`]}>
        <Routes>
          <Route path="/stand/zugang/:token" element={<StandTokenPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(localStorage.getItem(`hubiplan.stand.v2.${key}:detail`)).toBeNull())
    expect(screen.queryByText(detail.title)).toBeNull()
  },
)

it('erlaubt nur bei echtem Netzausfall den noch gültigen Offline-Stand', async () => {
  const token = 'abcdefghijkl-other-full-credential'
  const key = await standTokenKey(token)
  expect(key).not.toBe(await standTokenKey('abcdefghijkl-different-credential'))
  expect(key).not.toContain(token)
  authorizeStandCache(key, detail.stand_access.expires_at)
  saveStandCache(key, 'detail', detail, standRevision())
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
  render(
    <MemoryRouter initialEntries={[`/stand/zugang/${token}`]}>
      <Routes>
        <Route path="/stand/zugang/:token" element={<StandTokenPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText(detail.title)).toBeVisible()
})

it('entfernt bei verweigertem Mitgliederzugriff auch bereits geladene lokale Namen', async () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  authorizeStandCache(api.key)
  saveStandCache(api.key, 'local', local, standRevision())
  fakeApi({
    'GET /api/orgs/7/competitions/42/': () => ({ status: 200, body: detail }),
    'GET /api/orgs/7/competitions/42/starters/': () => ({ status: 200, body: [] }),
    'GET /api/orgs/7/competitions/42/members/': () => ({ status: 403 }),
  })
  const { result } = renderHook(() => useStandStore(api, () => 'Test'))
  await waitFor(() => expect(result.current.local.members).toEqual([]))
  expect(loadStandCache(api.key, 'local')).toBeNull()
})

it('begrenzt Offlinezugang auch ohne Server auf zwölf Stunden oder kürzere Tokenfrist', () => {
  bindStandUser(1)
  const api = orgStandApi(7, 42)
  const now = Date.now()
  authorizeStandCache(api.key)
  saveStandCache(api.key, 'local', local, standRevision())
  vi.spyOn(Date, 'now').mockReturnValue(now + 12 * 60 * 60 * 1000 + 1)
  expect(loadStandCache(api.key, 'local')).toBeNull()
  const tokenApi = tokenStandApi('test', 'token.short')
  authorizeStandCache(tokenApi.key, new Date(Date.now() + 10).toISOString())
  saveStandCache(tokenApi.key, 'local', local, standRevision())
  vi.mocked(Date.now).mockReturnValue(Date.now() + 11)
  expect(loadStandCache(tokenApi.key, 'local')).toBeNull()
})

it('sperrt einen alten Tab bei Kontowechsel in einem anderen Tab', async () => {
  let current = testUser
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { data: { user: current } },
    }),
  })
  render(
    <AuthProvider>
      <Account />
    </AuthProvider>,
  )
  await screen.findByText(testUser.email)
  current = { ...testUser, id: 999 }
  await act(async () => {
    window.dispatchEvent(
      new StorageEvent('storage', { key: 'hubiplan.stand.user', newValue: '999' }),
    )
  })
  await waitFor(() => expect(standUser()).toBe('999'))
})
