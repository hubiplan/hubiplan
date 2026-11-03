import { api } from './client.ts'

export interface Todo {
  id: number
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
}

export const todoBase = (org: number | null, department?: number | null) =>
  department ? `/api/depts/${department}/todos/` : `/api/orgs/${org}/todos/`

export const todoApi = {
  list: (base: string, trash = false) =>
    api.get<{ items: Todo[] }>(`${base}${trash ? '?trash=1' : ''}`),
  create: (base: string, values: unknown) => api.post<Todo>(base, values),
  update: (base: string, id: number, values: unknown) => api.patch<Todo>(`${base}${id}/`, values),
}
