// Hilfe: Angaben der Einheit (Ansprechpartner, Hinweise, Rechte) und abgehakte erste Schritte.
import { api } from './client.ts'

export interface HelpContact {
  name: string
  hint: string
  email: string
}

export interface HelpNote {
  text: string
  /** Name der Einheit, von der der Hinweis stammt */
  from: string
  /** von der gewählten Einheit selbst (änderbar) */
  own: boolean
}

export interface OrgHelp {
  /** eigene Ansprechpartner, sonst die der nächsten Einheit darüber */
  contacts: HelpContact[]
  contacts_from: { name: string; own: boolean } | null
  own_contacts: HelpContact[]
  /** Hinweise je Anleitung, von oben nach unten */
  notes: Record<string, HelpNote[]>
  /** Rollen der Einheit, die Rechte vergeben dürfen */
  admin_roles: string[]
  /** Beschriftung je Recht */
  rights: Record<string, string>
  can_edit: boolean
}

/** Rückmeldungen zu einem Hilfetext (Plattformverwaltung), ohne Person und Einheit. */
export interface HelpFeedbackEntry {
  key: string
  yes: number
  no: number
  comments: { id: number; text: string; day: string; language: string; version: string }[]
}

export interface HelpSearchMiss {
  id: number
  term: string
  language: string
  count: number
  last_day: string
}

export interface HelpFeedbackState {
  /** meiste „Nein“ zuerst */
  entries: HelpFeedbackEntry[]
  misses: HelpSearchMiss[]
}

const key = (k: string) => encodeURIComponent(k)

export const helpApi = {
  org: (orgId: number) => api.get<OrgHelp>(`/api/orgs/${orgId}/help/`),
  saveContacts: (orgId: number, contacts: HelpContact[]) =>
    api.patch<OrgHelp>(`/api/orgs/${orgId}/help/`, { contacts }),
  saveNote: (orgId: number, guide: string, text: string) =>
    api.put<OrgHelp>(`/api/orgs/${orgId}/help/notes/${key(guide)}/`, { text }),
  done: () => api.get<{ help_done: string[] }>('/api/me/help/'),
  check: (step: string) => api.post<{ help_done: string[] }>(`/api/me/help/${key(step)}/`, {}),
  uncheck: (step: string) => api.delWith<{ help_done: string[] }>(`/api/me/help/${key(step)}/`, {}),
  /** „Hat das geholfen?“: gespeichert ohne Person und Einheit */
  feedback: (entry: string, language: string, helpful: boolean, comment = '') =>
    api.post<unknown>('/api/help/feedback/', { key: entry, language, helpful, comment }),
  /** Suche ohne Treffer: nur die Suchwörter */
  searchMiss: (term: string, language: string) =>
    api.post<unknown>('/api/help/search-miss/', { term, language }),
  platformFeedback: () => api.get<HelpFeedbackState>('/api/platform/help-feedback/'),
  dropComment: (id: number) =>
    api.delWith<HelpFeedbackState>(`/api/platform/help-feedback/comments/${id}/`, {}),
  dropMiss: (id: number) =>
    api.delWith<HelpFeedbackState>(`/api/platform/help-feedback/misses/${id}/`, {}),
}
