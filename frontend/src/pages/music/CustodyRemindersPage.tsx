import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { useAutoSave, useLoad } from '../../components/forms.ts'
import { Alert, Field, SaveStatus } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { MusicHeader } from './MusicLayout.tsx'

type Preference = { enabled: boolean; days_ahead: number; scores: boolean; equipment: boolean }
/** Aufgaben › Erinnerungen für Noten und Ausstattung (Menüprüfung 2, N-05) */
export function MusicRemindersRoute() {
  const active = useOrg().active
  if (!active?.modules.includes('music') || !active.permissions.includes('music.view'))
    return <Navigate to="/aufgaben" replace />
  return <CustodyRemindersPage key={active.id} />
}

export function CustodyRemindersPage() {
  const org = useActiveOrg()
  return org.permissions.includes('todos.view') ? (
    <ReminderSettings />
  ) : (
    <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  )
}
function ReminderSettings() {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/custody-reminders/`
  const load = useLoad(() => api.get<Preference>(url), [org.id])
  return (
    <section className="stack music-page">
      <MusicHeader
        title={t('Persönliche Musikerinnerungen')}
        description={t('Rückgaben und Wartungen als eigene private Aufgaben vormerken.')}
      />
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {load.data && <ReminderForm initial={load.data} url={url} />}
      <Link to="/aufgaben">{t('Meine Aufgaben öffnen')}</Link>
    </section>
  )
}
function ReminderForm({ initial, url }: { initial: Preference; url: string }) {
  const org = useActiveOrg()
  const [value, setValue] = useState(initial)
  const [, setErrors] = useState<Record<string, string>>({})
  const canEdit = org.permissions.includes('todos.edit')
  // Die Schnittstelle nimmt die Auswahl immer als Ganzes
  const auto = useAutoSave(
    { values: value, setErrors, setValues: setValue },
    (_changes, all) => api.post<Preference>(url, all),
    { enabled: canEdit },
  )
  return (
    <form className="card stack" onSubmit={(e) => e.preventDefault()}>
      <p>
        {t(
          'Nur für dich und nur nach Aktivierung. Fällige Rückgaben und Wartungen erzeugen private Aufgaben; Benachrichtigungen folgen deinen vorhandenen Aufgabeneinstellungen. Es werden keine Aufgaben an andere Personen verteilt.',
        )}
      </p>
      {canEdit && <SaveStatus auto={auto} />}
      <fieldset className="stack" disabled={!canEdit}>
        <legend>{t('Meine Erinnerungsauswahl')}</legend>
        <label>
          <input
            type="checkbox"
            checked={value.enabled}
            onChange={(e) => setValue({ ...value, enabled: e.target.checked })}
          />{' '}
          {t('Musikerinnerungen aktivieren')}
        </label>
        <Field
          type="number"
          label={t('Aufgaben so viele Tage vorher anlegen')}
          min={0}
          max={30}
          required
          value={value.days_ahead}
          onChange={(e) => setValue({ ...value, days_ahead: Number(e.target.value) })}
        />
        <label>
          <input
            type="checkbox"
            checked={value.scores}
            onChange={(e) => setValue({ ...value, scores: e.target.checked })}
          />{' '}
          {t('Notenrückgaben')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.equipment}
            onChange={(e) => setValue({ ...value, equipment: e.target.checked })}
          />{' '}
          {t('Rückgaben und Wartungen der Ausstattung')}
        </label>
      </fieldset>
      <p className="muted">
        {t(
          'Unveränderte Erinnerungsaufgaben werden nach Rückgabe oder Wartung automatisch erledigt. Selbst bearbeitete oder gelöschte Aufgaben werden nicht überschrieben oder erneut angelegt. Ein neuer Fälligkeitstag erzeugt eine neue Erinnerung.',
        )}
      </p>
    </form>
  )
}
