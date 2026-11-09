// Ausgeblendete Schnellaktionen der Startseite am eigenen Konto (S-04); „*“ = alle.
import { api } from './client.ts'

export interface HomeActionsData {
  hidden: string[]
}

export const homeActionsApi = {
  get: () => api.get<HomeActionsData>('/api/me/home-actions/'),
  update: (hidden: string[]) => api.put<HomeActionsData>('/api/me/home-actions/', { hidden }),
}
