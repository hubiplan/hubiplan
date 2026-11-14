// Gespeicherte Orte (Einstellungen › Orte und Ortsfelder in Formularen).
import { api } from './client.ts'

/** Was ein Formular beim Auswählen übernimmt (Räume: Anschrift usw. vom Gebäude) */
export interface PlacePick {
  name: string
  address: string
  directions: string
  latitude: number | null
  longitude: number | null
}

export interface Place {
  id: number
  /** Gesetzt: Raum in diesem Ort (Gebäude) */
  parent: number | null
  name: string
  /** „Gebäude, Raum“ bei Räumen, sonst der Name */
  full_name: string
  pick: PlacePick
  address: string
  directions: string
  latitude: number | null
  longitude: number | null
  is_active: boolean
  /** Ort dieser Einheit (sonst: des Dachverbands bzw. Vereins darüber) */
  own: boolean
  owner: string | null
  can_edit: boolean
}

export interface PlaceList {
  places: Place[]
  can_edit: boolean
  can_manage: boolean
}

export interface PlaceSuggestion {
  name: string
  address: string
  count: number
}

export type PlaceInput = Partial<
  Pick<Place, 'parent' | 'name' | 'address' | 'directions' | 'latitude' | 'longitude' | 'is_active'>
>

export const placeApi = {
  list: (base: string, all = false) => api.get<PlaceList>(all ? `${base}?alle=1` : base),
  create: (base: string, data: PlaceInput) => api.post<Place>(base, data),
  update: (base: string, id: number, data: PlaceInput) => api.patch<Place>(`${base}${id}/`, data),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  suggestions: (base: string) => api.get<PlaceSuggestion[]>(`${base}suggestions/`),
}
