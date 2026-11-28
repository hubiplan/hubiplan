// Gemeinsame Helfer, Typen und Konstanten von MusicPage.

export type Row = { id: number; [key: string]: string | number | boolean | null }
export type Field = {
  key: string
  label: string
  type?: string
  options?: [string, string][]
  /** Mitglied per Suche wählen statt aus einer Liste aller Mitglieder */
  member?: boolean
  optional?: boolean
  initial?: number
  min?: number
  max?: number
  /** Weitere Felder vorschlagen, wenn sich dieses ändert (z. B. Art → Spielform, Uniform) */
  suggest?: (value: string) => Record<string, string | number | boolean>
  /** Feld gesperrt, solange diese Bedingung gilt (z. B. Auftraggeber bei weiterem Tag) */
  lockedBy?: (values: Record<string, string | number | boolean>) => string | null
}
/** Bereich aus der Adresse /musik/<bereich> */
export function musicArea(pathname: string): string {
  return pathname.replace(/^\/musik\/?/, '').split('/')[0] ?? ''
}
