// Startseite am eigenen Konto (S-04): ausgeblendete Schnellaktionen des Vorschlags („*“ = alle),
// je Arbeitsbereich („o12“, „d5“) die eigene Auswahl in Reihenfolge und die Anordnung der Blöcke.
import { api } from './client.ts'

/** Anordnung der Blöcke in einem Arbeitsbereich */
export interface HomeLayout {
  order: string[]
  hidden: string[]
  wide: string[]
}

export interface HomeActionsData {
  hidden: string[]
  /** Fehlt ein Bereich, gilt der Vorschlag der Rollen */
  chosen?: Record<string, string[]>
  /** Fehlt ein Bereich, gilt die Standardanordnung */
  layout?: Record<string, HomeLayout>
}

export interface HomeActionsUpdate {
  hidden?: string[]
  /** null stellt im Bereich wieder den Vorschlag her */
  chosen?: Record<string, string[] | null>
  /** null stellt im Bereich wieder die Standardanordnung her */
  layout?: Record<string, HomeLayout | null>
}

export const homeActionsApi = {
  get: () => api.get<HomeActionsData>('/api/me/home-actions/'),
  update: (body: HomeActionsUpdate) => api.put<HomeActionsData>('/api/me/home-actions/', body),
}
