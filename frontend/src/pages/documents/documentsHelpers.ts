// Gemeinsame Helfer, Typen und Konstanten von DocumentsPage.
import './documents.css'
import type { DocBase, DocFolder, Visibility } from '../../api/documents.ts'

export const MAX_BYTES = 20 * 1024 * 1024
export const ACCEPT =
  '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.jpg,.jpeg,.png,.txt,.csv,.musicxml,.mxl,.xml,.mei,.abc,.mid,.midi,application/pdf,image/jpeg,image/png'

export type Msg = { kind: 'error' | 'success'; text: string } | null

export interface FolderCtx {
  base: DocBase
  manage: boolean
  busy: boolean
  run: (action: () => Promise<unknown>, success?: string) => Promise<void>
  folders: DocFolder[]
  visibilities: { value: Visibility; label: string }[]
  setMessage: (m: Msg) => void
  shareUp: string | null
}
