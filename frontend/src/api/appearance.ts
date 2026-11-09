// Darstellung der Web-App am eigenen Konto: wie Gerät, hell oder dunkel (X-02).
import { api } from './client.ts'
import type { ColorSchemeChoice } from '../theme/colorScheme.ts'

export interface AppearanceData {
  color_scheme: ColorSchemeChoice
}

export const appearanceApi = {
  get: () => api.get<AppearanceData>('/api/me/appearance/'),
  update: (color_scheme: ColorSchemeChoice) =>
    api.patch<AppearanceData>('/api/me/appearance/', { color_scheme }),
}
