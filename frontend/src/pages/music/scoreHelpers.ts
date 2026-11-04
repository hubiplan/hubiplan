import { t } from '../../i18n/index.ts'

export const formats = (): [string, string][] => [
  ['concert', t('Konzertformat')],
  ['march', t('Marschbuchformat')],
]

export const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
