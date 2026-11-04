import { useState } from 'react'
import { api } from '../api/client.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError, SelectField } from './ui.tsx'
import { t } from '../i18n/index.ts'

interface ReminderConfig {
  days: number[]
  enabled: boolean
  mail: boolean | null
  push: boolean | null
}

export function TodoReminders({ base, id }: { base: string; id: number }) {
  const endpoint = `${base}${id}/reminders/`
  const { data, error, reload, setData } = useLoad(
    () => api.get<ReminderConfig>(endpoint),
    [endpoint],
  )
  const [saveError, setSaveError] = useState<string | null>(null)
  async function change(patch: Partial<ReminderConfig>) {
    try {
      setData(await api.patch<ReminderConfig>(endpoint, patch))
      setSaveError(null)
    } catch (err) {
      setSaveError(errorMessage(err))
    }
  }
  return (
    <details className="card">
      <summary>{t('Meine Erinnerungen')}</summary>
      {error && <LoadError message={error} onRetry={reload} />}
      {saveError && <p role="alert">{saveError}</p>}
      {data && (
        <>
          <Checkbox
            label={t('Für diese Aufgabe erinnern')}
            checked={data.enabled}
            onChange={(value) => void change({ enabled: value })}
          />
          {[
            [0, t('Am Tag der Frist')],
            [1, t('1 Tag vorher')],
            [3, t('3 Tage vorher')],
            [7, t('1 Woche vorher')],
          ].map(([offset, label]) => (
            <Checkbox
              key={offset}
              label={String(label)}
              checked={data.days.includes(Number(offset))}
              onChange={(value) =>
                void change({
                  days: value
                    ? [...data.days, Number(offset)]
                    : data.days.filter((day) => day !== offset),
                })
              }
            />
          ))}
          {(['mail', 'push'] as const).map((channel) => (
            <SelectField
              key={channel}
              label={channel === 'mail' ? t('Mail') : t('Push')}
              value={data[channel] === null ? 'default' : String(data[channel])}
              onChange={(event) =>
                void change({
                  [channel]:
                    event.target.value === 'default' ? null : event.target.value === 'true',
                })
              }
            >
              <option value="default">{t('Vorgabe aus Mein Konto')}</option>
              <option value="true">{t('Ein')}</option>
              <option value="false">{t('Aus')}</option>
            </SelectField>
          ))}
          <p className="muted">
            {t(
              'Bei Überfälligkeit folgt am nächsten Tag um 8 Uhr genau eine zusätzliche Erinnerung. Die Hervorhebung in HUBIplan bleibt immer aktiv.',
            )}
          </p>
        </>
      )}
    </details>
  )
}
