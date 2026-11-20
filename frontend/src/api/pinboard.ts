// Pinnwand: kurze Beiträge an die Mitglieder (Lückenliste 20.11.2026, A3)
import { api } from './client.ts'

export interface NoticePhoto {
  id: number
  url: string
  width: number
  height: number
}

export interface Notice {
  id: number
  text: string
  /** Name der Untereinheit, leer beim Verein */
  unit: string
  department: number | null
  /** Verein oder Untereinheit, von der der Beitrag kommt */
  from: string
  author: string
  pinned: boolean
  visible_until: string | null
  created_at: string
  edited_at: string | null
  push: boolean
  pushed: boolean
  expired: boolean
  version: number
  can_edit: boolean
  photos: NoticePhoto[]
  /** Nur im Mitgliederbereich: seit dem letzten Lesen neu */
  new?: boolean
}

export interface NoticeDraft {
  text: string
  pinned: boolean
  visible_until: string
  push: boolean
  photos: File[]
  /** Nur im Mitgliederbereich: Ziel (leer: Verein) */
  department?: number | null
}

export interface NoticeList {
  notices: Notice[]
  can_edit?: boolean
  targets?: { department: number | null; name: string }[]
  max_photos: number
  max_text: number
}

function form(draft: NoticeDraft) {
  const data = new FormData()
  data.append('text', draft.text)
  data.append('pinned', draft.pinned ? '1' : '0')
  data.append('push', draft.push ? '1' : '0')
  if (draft.visible_until) data.append('visible_until', draft.visible_until)
  if (draft.department != null) data.append('department', String(draft.department))
  for (const file of draft.photos) data.append('photos', file)
  return data
}

export const pinboardApi = {
  list: (base: string) => api.get<NoticeList>(base),
  create: (base: string, draft: NoticeDraft) => api.post<Notice>(base, form(draft)),
  update: (
    base: string,
    notice: Notice,
    data: { text?: string; pinned?: boolean; visible_until?: string | null },
  ) => api.patch<Notice>(`${base}${notice.id}/`, { ...data, version: notice.version }),
  remove: (base: string, id: number) => api.del(`${base}${id}/`),
  addPhotos: (base: string, id: number, files: File[]) => {
    const data = new FormData()
    for (const file of files) data.append('photos', file)
    return api.post<Notice>(`${base}${id}/photos/`, data)
  },
  removePhoto: (base: string, id: number, photo: number) =>
    api.del(`${base}${id}/photos/${photo}/`) as Promise<Notice>,
}

export const portalPinboardBase = (access: number) => `/api/portal/${access}/pinboard/`
