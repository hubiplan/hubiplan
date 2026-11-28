// Gemeinsame Helfer, Typen und Konstanten von AppearancePage.
import type { PaletteRole } from '../../api/orgs.ts'
import { t } from '../../i18n/index.ts'

/** Beschriftung der Farbrollen (Einstellungen, Hinweise) */
export function roleLabel(role: PaletteRole): string {
  switch (role) {
    case 'text':
      return t('Fließtext')
    case 'muted':
      return t('Sekundärtext')
    case 'surface':
      return t('Flächen und Tabellenzeilen')
    case 'background':
      return t('Hintergrund')
  }
}
