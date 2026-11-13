// Link zum Hochladen von Bildern für die Webseite (KI-Schnittstelle W2, docs/mcp.md).
import { parseBody, send } from './client.ts'

export interface ImageUploadInfo {
  organization: string
  imprint_key?: string
  logo_url: string | null
  theme: { primary: string; on_primary: string; accent: string; on_accent: string }
  expires_at: string
  remaining: number
}

const path = (token: string) => `/api/public/website-images/${encodeURIComponent(token)}/`

// Ohne Sitzung und CSRF-Token: der Link ist der Ausweis
async function call(token: string, init: RequestInit) {
  const res = await send(path(token), { ...init, credentials: 'omit' })
  return { status: res.status, body: parseBody(await res.text()) as Record<string, unknown> }
}

export const imageUploadApi = {
  info: async (token: string) => {
    const result = await call(token, { method: 'GET' })
    return { status: result.status, body: result.body as unknown as ImageUploadInfo }
  },
  upload: (token: string, file: File) => {
    const form = new FormData()
    form.append('file', file, file.name || 'bild.jpg')
    return call(token, { method: 'POST', body: form })
  },
}
