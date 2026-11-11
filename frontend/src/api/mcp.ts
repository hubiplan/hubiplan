// KI-Assistenten verbinden (Backend: App mcpserver, docs/mcp.md Stufe 1a).
import { api } from './client.ts'

export interface McpScope {
  scope: string
  label: string
}

/** Was die Seite „KI-Assistent verbinden“ über die Anfrage weiß. */
export interface McpRequest {
  client: string
  redirect_host: string
  scopes: McpScope[]
  units: { id: number; name: string }[]
  /** Leer: zweiter Faktor in Ordnung; sonst der Hinweis, was fehlt */
  problem: string
}

export interface McpDenied {
  detail?: string
  /** Rückleitung mit Fehler an den Assistenten (leer: nicht zurückleiten) */
  redirect?: string
}

export interface McpConnection {
  id: number
  client: string
  organization: string
  scopes: McpScope[]
  created_at: string
  last_used_at: string
  expires_at: string
}

export interface McpConnections {
  enabled: boolean
  /** Adresse, die man im Assistenten einträgt */
  address: string
  connections: McpConnection[]
}

export const mcpApi = {
  describe: (query: string) => api.get<McpRequest>(`/api/mcp/oauth/authorize/?${query}`),
  allow: (params: Record<string, string>, organization: number) =>
    api.post<{ redirect: string }>('/api/mcp/oauth/authorize/', { params, organization }),
  deny: (params: Record<string, string>) =>
    api.post<{ redirect: string }>('/api/mcp/oauth/authorize/', { params, deny: true }),
  connections: () => api.get<McpConnections>('/api/me/mcp/'),
  disconnect: (id: number) => api.del(`/api/me/mcp/${id}/`),
}
