// Gemeinsame Helfer, Typen und Konstanten von TextEditor.
import 'prosemirror-view/style/prosemirror.css'
import type { WebsiteImage } from '../../api/website.ts'
import { t } from '../../i18n/index.ts'

export function imageLabel(i: WebsiteImage): string {
  return i.caption || i.alt_text || t('Bild {key}', { key: i.key })
}
