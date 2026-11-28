import { useRef } from 'react'
import type { CalendarBase, EventCategory, EventUnit } from '../../api/events.ts'
import { EventForm } from './EventForm.tsx'
import { Modal } from '../Modal.tsx'
import type { CloseGuard } from './eventFormHelpers.ts'
import { t } from '../../i18n/index.ts'

export { Modal }

/** Neuen Termin anlegen (Dialog). */
export function NewEventDialog({
  base,
  date,
  categories,
  units,
  rsvpAllowed,
  onClose,
  onSaved,
}: {
  base: CalendarBase
  date: string
  categories: EventCategory[]
  units?: EventUnit[]
  rsvpAllowed?: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const guard = useRef<CloseGuard | null>(null)
  return (
    <Modal
      title={t('Neuer Termin')}
      onClose={onClose}
      beforeClose={() => guard.current?.() ?? true}
    >
      <EventForm
        guardRef={guard}
        base={base}
        event={null}
        date={date}
        categories={categories}
        units={units}
        rsvpAllowed={rsvpAllowed}
        onCancel={onClose}
        onSaved={onSaved}
      />
    </Modal>
  )
}
