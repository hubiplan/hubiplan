// Schnellaktionen der Startseite am eigenen Konto (S-04): ausgeblendete Aktionen des Vorschlags
// („*“ = alle) und je Arbeitsbereich („o12“, „d5“) die eigene Auswahl in Reihenfolge.
import { api } from './client.ts'

export interface HomeActionsData {
  hidden: string[]
  /** Fehlt ein Bereich, gilt der Vorschlag der Rollen */
  chosen?: Record<string, string[]>
}

export interface HomeActionsUpdate {
  hidden?: string[]
  /** null stellt im Bereich wieder den Vorschlag her */
  chosen?: Record<string, string[] | null>
}

export const homeActionsApi = {
  get: () => api.get<HomeActionsData>('/api/me/home-actions/'),
  update: (body: HomeActionsUpdate) => api.put<HomeActionsData>('/api/me/home-actions/', body),
}
