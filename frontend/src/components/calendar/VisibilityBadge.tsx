import { Modal } from '../Modal.tsx'
import { t } from '../../i18n/index.ts'

export { Modal }

export function VisibilityBadge({ visibility }: { visibility: string }) {
  if (visibility === 'members') return null
  return (
    <span className={`badge badge-${visibility}`}>
      {visibility === 'public' ? t('nach außen öffentlich') : t('nur Vorstand')}
    </span>
  )
}
