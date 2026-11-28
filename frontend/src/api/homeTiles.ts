// Kacheln der Startseite, die bei Anlass von selbst erscheinen (backend/hometiles). Dieselbe
// Schnittstelle nutzen Android und iOS; der Server liefert fertige Texte.
import { api } from './client.ts'

export type TileState = 'auto' | 'on' | 'off'
export type TileTone = 'good' | 'warn' | 'bad' | null

export interface TileFigure {
  label: string
  value: string
  tone: TileTone
}

export interface TileRow {
  title: string
  detail: string
  link: string | null
  tone: TileTone
}

export interface TileContent {
  figures: TileFigure[]
  rows: TileRow[]
  text: string
  link: string | null
  link_label: string
  /** Aktueller Anlass; leer = keiner */
  reason: string
}

export interface HomeTile {
  key: string
  title: string
  description: string
  state: TileState
  urgent: boolean
  /** Bei „bei Anlass“ auch ohne Anlass zu sehen (z. B. Kasse im reinen Kassenbuch) */
  default_on?: boolean
  shown: boolean
  /** null bei „nie“ */
  content: TileContent | null
}

export interface HomeTilesData {
  scope: string
  tiles: HomeTile[]
}

export const homeTilesApi = {
  org: (orgId: number) => api.get<HomeTilesData>(`/api/orgs/${orgId}/home-tiles/`),
  portal: (accessId: number) => api.get<HomeTilesData>(`/api/portal/${accessId}/home-tiles/`),
}
