// Anmeldung an der Nextcloud mit dem HUBIplan-Konto (Backend: App oidc).
import { api } from './client.ts'

export type NextcloudAudience = 'board' | 'roles' | 'members'

export interface NextcloudClient {
  id: number
  name: string
  base_url: string
  client_id: string
  audience: NextcloudAudience
  require_mfa: boolean
  /** Anmeldung nur mit PKCE (S256), Fachfrage FQ26 */
  require_pkce?: boolean
  groups_board: boolean
  groups_roles: boolean
  groups_units: boolean
  groups_members: boolean
  // Je Zeile „E-Mail = Benutzername“ (bisherige Nextcloud-Konten)
  usernames: string
  // Rollen-ID → Gruppen in der Nextcloud (statt des Rollennamens)
  role_groups: Record<string, string[]>
  // Alle Rollen der Einheit für die Zuordnung (auch Ämter in Untereinheiten)
  role_choices: NextcloudRoleChoice[]
  // Gespeicherte Zeilen auf Verwaltungs- oder Dienstkonten (werden nie zugeordnet)
  blocked_usernames?: string[]
  // Konten in der Nextcloud deaktivieren, wenn der Zugang endet
  manage_accounts: boolean
  service_user: string
  has_service_password: boolean
  account_group: string
  sync_error: string
  synced_at: string | null
  // Termine per CalDAV in Kalender der Nextcloud schreiben (nur lesend freigegeben)
  calendar_members: boolean
  calendar_members_group: string
  calendar_board: boolean
  calendar_board_group: string
  calendar_error: string
  calendar_synced_at: string | null
  // Gruppen laufend abgleichen (nicht nur beim Anmelden)
  sync_groups: boolean
  // Gruppen, die HUBIplan setzt und entfernt, als Text „A, B“
  sync_groups_list: string
  groups_error: string
  groups_synced_at: string | null
  // In Nextcloud ablegen (Ordner im Dienstkonto, nur lesend an Gruppen freigegeben)
  files_enabled: boolean
  files_root: string
  files_board_group: string
  files_finance_group: string
  files_members_group: string
  // Art → Jahre (0: dauerhaft), nur abweichende
  files_retention: Record<string, number>
  // Aus Nextcloud übernehmen: Ordner, den der Verein dem Dienstkonto freigegeben hat
  files_source: string
  files_error: string
  // Videoraum am Termin (Talk); nach so vielen Tagen nach dem Termin gelöscht
  talk_enabled: boolean
  talk_keep_days: number
  is_active: boolean
  created_at: string
  last_used_at: string | null
  redirect_uri: string
  discovery_url: string
  // Nur direkt nach Anlegen oder Erneuern
  client_secret?: string
}

export interface NextcloudRoleChoice {
  id: number
  name: string
  // Untereinheit (leer: Rolle der Einheit selbst)
  unit: string
  is_board: boolean
}

export type NextcloudInput = Partial<
  Pick<
    NextcloudClient,
    | 'name'
    | 'base_url'
    | 'audience'
    | 'require_mfa'
    | 'require_pkce'
    | 'groups_board'
    | 'groups_roles'
    | 'groups_units'
    | 'groups_members'
    | 'usernames'
    | 'manage_accounts'
    | 'service_user'
    | 'account_group'
    | 'calendar_members'
    | 'calendar_members_group'
    | 'calendar_board'
    | 'calendar_board_group'
    | 'sync_groups'
    | 'sync_groups_list'
    | 'files_enabled'
    | 'files_root'
    | 'files_board_group'
    | 'files_finance_group'
    | 'files_members_group'
    | 'files_retention'
    | 'files_source'
    | 'talk_enabled'
    | 'talk_keep_days'
    | 'is_active'
  >
> & {
  // Nur schreiben; leer lässt das gespeicherte
  service_password?: string
  // Je Rolle die Gruppen als Text „A, B“ (leer: Rollenname)
  role_groups?: Record<string, string>
}

export interface NextcloudAccount {
  id: number
  nc_user: string
  email: string
  name: string
  first_login_at: string
  last_login_at: string
  disabled_by_hubiplan: boolean
  changed_at: string | null
  error: string
  // Was der nächste Abgleich täte
  planned: '' | 'disable' | 'enable'
}

export interface NextcloudSyncResult {
  result: { disabled: number; enabled: number; errors: number; held: boolean }
  client: NextcloudClient
}

export interface NextcloudCalendarCounts {
  written?: number
  deleted?: number
  unchanged?: number
  removed?: boolean
}

export interface NextcloudCalendarResult {
  result: { members?: NextcloudCalendarCounts; board?: NextcloudCalendarCounts; error: string }
  client: NextcloudClient
}

export interface NextcloudGroupAccount {
  id: number
  nc_user: string
  email: string
  name: string
  // Abgeglichene Gruppen, in denen das Konto heute ist
  current: string[]
  add: string[]
  remove: string[]
  error: string
  // Das Konto gibt es in der Nextcloud nicht (mehr); ``error`` sagt, was zu tun ist
  missing?: boolean
}

export interface NextcloudGroupReport {
  managed: string[]
  // Gruppen, für die das Dienstkonto kein Gruppen-Admin ist (soweit bekannt)
  missing_admin: string[]
  accounts: NextcloudGroupAccount[]
}

export interface NextcloudGroupSyncResult {
  result: { added: number; removed: number; errors: number; missing?: number; held: boolean }
  client: NextcloudClient
}

const base = (org: number) => `/api/orgs/${org}/nextcloud/`

export const nextcloudApi = {
  list: (org: number) => api.get<NextcloudClient[]>(base(org)),
  create: (org: number, data: NextcloudInput) => api.post<NextcloudClient>(base(org), data),
  update: (org: number, id: number, data: NextcloudInput) =>
    api.patch<NextcloudClient>(`${base(org)}${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}${id}/`),
  renewSecret: (org: number, id: number) => api.post<NextcloudClient>(`${base(org)}${id}/secret/`),
  accounts: (org: number, id: number) => api.get<NextcloudAccount[]>(`${base(org)}${id}/accounts/`),
  check: (org: number, id: number) =>
    api.post<{ ok: boolean; detail: string }>(`${base(org)}${id}/check/`),
  sync: (org: number, id: number, confirm = false) =>
    api.post<NextcloudSyncResult>(`${base(org)}${id}/sync/`, { confirm }),
  groups: (org: number, id: number) => api.get<NextcloudGroupReport>(`${base(org)}${id}/groups/`),
  syncGroups: (org: number, id: number, confirm = false) =>
    api.post<NextcloudGroupSyncResult>(`${base(org)}${id}/groups/`, { confirm }),
  calendars: (org: number, id: number) =>
    api.post<NextcloudCalendarResult>(`${base(org)}${id}/calendars/`),
}

export interface NextcloudService {
  name: string
  organization: string
  url: string
}

export interface NextcloudDenied {
  detail: string
  redirect?: string
  back?: string
}

export const oidcApi = {
  describe: (query: string) => api.get<NextcloudService>(`/api/oidc/authorize/?${query}`),
  authorize: (params: Record<string, string>) =>
    api.post<{ redirect: string }>('/api/oidc/authorize/', params),
}

// Dateien mit der Nextcloud: ablegen und übernehmen
export type NextcloudTarget = 'board' | 'finance' | 'members'
export type NextcloudCategory =
  'records' | 'finance' | 'statistics' | 'reports' | 'personal' | 'other'

export interface NextcloudFilesStatus {
  store: boolean
  name: string
  targets: { key: NextcloudTarget; label: string; folder: string; group: string }[]
  // years null: dauerhaft
  categories: { key: NextcloudCategory; label: string; years: number | null }[]
  pick: boolean
}

export interface NextcloudEntry {
  name: string
  path: string
  is_dir: boolean
  size: number
  modified: string
  content_type: string
}

const files = (org: number) => `/api/orgs/${org}/nextcloud-dateien/`

export const nextcloudFilesApi = {
  status: (org: number) => api.get<NextcloudFilesStatus>(files(org)),
  store: (org: number, data: FormData) =>
    api.post<{ path: string; delete_after: string | null }>(files(org), data),
  list: (org: number, path: string) =>
    api.get<NextcloudEntry[]>(`${files(org)}quelle/?pfad=${encodeURIComponent(path)}`),
  fileUrl: (org: number, path: string) =>
    `${files(org)}quelle/datei/?pfad=${encodeURIComponent(path)}`,
}
