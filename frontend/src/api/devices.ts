// Android-App: Geräte verbinden (QR-Code) und angemeldete Geräte verwalten.
import { api } from './client.ts'

export interface AppDevice {
  id: number
  name: string
  platform: 'android' | 'ios' | 'other'
  app_version: string
  push: string
  created_at: string
  last_seen_at: string
  current: boolean
  // Verwaltung in der App freigeschaltet bis (Vorstandszugang), sonst null
  admin_until?: string | null
}

export interface PairingCode {
  id: number
  url: string
  expires_at: string
}

export interface PairingStatus {
  used: boolean
  device: string | null
  expires_at: string
}

export interface BrowserUnlock {
  device: string
  confirmed: boolean
  redirect?: string
}

export const devicesApi = {
  list: () => api.get<AppDevice[]>('/api/app/v1/devices/'),
  remove: (id: number) => api.del(`/api/app/v1/devices/${id}/`),
  lockAdmin: (id: number) => api.del(`/api/app/v1/devices/${id}/admin/`),
  // challenge: Prüfwert der App, die /app/anmelden geöffnet hat (APP-01); beim QR-Code leer
  pairingCode: (challenge?: string) =>
    api.post<PairingCode>('/api/app/v1/pairing/', challenge ? { challenge } : {}),
  pairingStatus: (id: number) => api.get<PairingStatus>(`/api/app/v1/pairing/${id}/`),
  // Verwaltung der iPhone-App im Browser freischalten (devices/browser_unlock.py)
  browserUnlock: (ticket: string, confirm: boolean) =>
    api.post<BrowserUnlock>('/api/app/v1/admin/unlock/browser/confirm/', { ticket, confirm }),
  // Mitgliederbereich oder etwas zu verwalten; ältere Server melden nur den Mitgliederbereich
  mayConnect: () =>
    api
      .get<{ portal: unknown[]; app?: boolean }>('/api/me/contexts/')
      .then((c) => c.app ?? c.portal.length > 0),
}
