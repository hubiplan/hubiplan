// Versammlungen V7: Hilfen für Anmelden per App (docs/versammlungen.md).
import type { LiveState, MeetingStatus } from '../../api/meetings.ts'

export const LIVE_STATES: MeetingStatus[] = ['draft', 'invited', 'held']

/** Adresse im QR-Code: öffnet den Mitgliederbereich; die App liest Versammlung und Code. */
export function checkinLink(state: LiveState) {
  const params = new URLSearchParams({ v: String(state.organization), c: state.code ?? '' })
  return `${window.location.origin}/mein-bereich/versammlungen/da/${state.meeting}?${params}`
}
