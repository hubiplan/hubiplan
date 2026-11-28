// Gemeinsame Helfer, Typen und Konstanten der Plattformseiten.
import { t } from '../../i18n/index.ts'

export const ACCESS_LABELS = {
  get none() {
    return t('kein Zugriff')
  },
  get read() {
    return t('nur lesen')
  },
  get write() {
    return t('lesen und ändern')
  },
}
