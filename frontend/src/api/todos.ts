import { api } from './client.ts'

export interface TodoShare {
  target_org?: number
  target_department?: number | null
  user?: number | null
  role?: number | null
  level: 'view' | 'edit'
  responsible: boolean
}

export interface Todo {
  id: number
  organization?: number
  department?: number | null
  per_unit?: boolean
  distributed?: boolean
  central_readonly?: boolean
  local_note?: string
  can_complete?: boolean
  series?: {
    id: number
    version: number
    sequence_no: number
    active: boolean
    repeat: 'daily' | 'weekly' | 'monthly' | 'yearly'
    interval: number
    basis: 'due' | 'done'
    last_day: boolean
    ends_on: string | null
    count: number | null
    deleted_at: string | null
  } | null
  title: string
  description: string
  due_date: string | null
  due_time: string | null
  timezone: string
  status: 'open' | 'done'
  shared: boolean
  created_by: number | null
  owner: number | null
  version: number
  created_at: string
  updated_at: string
  deleted_at: string | null
  can_edit: boolean
  can_delete: boolean
  overdue?: boolean
  highlight?: boolean
  due_label?: string
  can_share?: boolean
  can_take_over?: boolean
  shares?: TodoShare[]
  owners?: { id: number; name: string }[]
}

export const todoBase = (org: number | null, department?: number | null) =>
  department ? `/api/depts/${department}/todos/` : `/api/orgs/${org}/todos/`

export const todoApi = {
  get: (base: string, id: number) => api.get<Todo>(`${base}${id}/`),
  list: (base: string, trash = false) =>
    api.get<{ items: Todo[] }>(`${base}${trash ? '?trash=1' : ''}`),
  create: (base: string, values: unknown) => api.post<Todo>(base, values),
  update: (base: string, id: number, values: unknown) => api.patch<Todo>(`${base}${id}/`, values),
}
