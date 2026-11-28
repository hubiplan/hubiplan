// Gemeinsame Helfer, Typen und Konstanten von EventForm.
import type { Repeat, Visibility } from '../../api/events.ts'

/** Prüft vor dem Schließen des Dialogs, ob Eingaben verloren gingen; false = offen lassen. */
export type CloseGuard = () => Promise<boolean>

export interface Values {
  title: string
  /** Untereinheit, für die der Termin gilt; '' = die Einheit selbst */
  unit: string
  description: string
  /** Ablauf oder Programm (Infoschreiben an Angemeldete) */
  programme: string
  location: string
  address: string
  directions: string
  latitude: string
  longitude: string
  category: string
  all_day: boolean
  hide_end_time: boolean
  start_date: string
  start_time: string
  end_date: string
  end_time: string
  visibility: Visibility
  repeat: Repeat
  repeat_interval: string
  repeat_until: string
  is_cancelled: boolean
  cancel_note: string
  rsvp_enabled: boolean
  rsvp_deadline_date: string
  rsvp_deadline_time: string
  rsvp_capacity: string
  rsvp_guests: boolean
  rsvp_maybe: boolean
  rsvp_note: boolean
  rsvp_note_question: string
  remind: boolean
  remind_days: string
  notify: boolean
  share_up: Share
  share_down: Share
}

/** Weitergabe am Termin: '' = wie voreingestellt */
export type Share = '' | 'yes' | 'no'
