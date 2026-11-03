import { api } from '../api/client.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError } from './ui.tsx'
import { useState } from 'react'
import { t } from '../i18n/index.ts'

export function TodoPreferences() {
  const { data, error, reload, setData } = useLoad(
    () => api.get<Record<string, boolean>>('/api/me/todos/preferences/'),
    [],
  )
  const [saveError, setSaveError] = useState<string | null>(null)
  async function change(key: string, value: boolean) {
    try {
      setData(
        await api.patch<Record<string, boolean>>('/api/me/todos/preferences/', { [key]: value }),
      )
      setSaveError(null)
    } catch (err) {
      setSaveError(errorMessage(err))
    }
  }
  return (
    <div className="card">
      <h2>{t('Benachrichtigungen zu Aufgaben')}</h2>
      {error && <LoadError message={error} onRetry={reload} />}
      {saveError && <p role="alert">{saveError}</p>}
      {data && (
        <>
          <Checkbox
            label={t('Beim Teilen per Mail informieren')}
            checked={data.share_mail}
            onChange={(v) => void change('share_mail', v)}
          />
          <Checkbox
            label={t('Beim Teilen per Push informieren')}
            checked={data.share_push}
            onChange={(v) => void change('share_push', v)}
          />
          <Checkbox
            label={t('Aufgabentitel im Push zeigen')}
            checked={data.push_title}
            onChange={(v) => void change('push_title', v)}
          />
        </>
      )}
    </div>
  )
}
