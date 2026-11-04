import { useState } from 'react'
import { api } from '../api/client.ts'
import { errorMessage, useLoad } from './forms.ts'
import { Checkbox, LoadError } from './ui.tsx'
import { t } from '../i18n/index.ts'

export function TodoCleanup({ base }: { base: string }) {
  const { data, error, reload, setData } = useLoad(
    () => api.get<{ purge_done: boolean }>(`${base}cleanup/`),
    [base],
  )
  const [saveError, setSaveError] = useState<string | null>(null)
  return (
    <section className="stack-sm">
      <h3>{t('Aufbewahrung geteilter Aufgaben')}</h3>
      {error && <LoadError message={error} onRetry={reload} />}
      {saveError && <p role="alert">{saveError}</p>}
      {data && (
        <Checkbox
          label={t(
            'Erledigte einmalige Aufgaben dieser Einheit nach 12 Monaten in den Papierkorb verschieben',
          )}
          checked={data.purge_done}
          onChange={(value) => {
            void api
              .patch<{ purge_done: boolean }>(`${base}cleanup/`, { purge_done: value })
              .then(setData)
              .catch((err: unknown) => setSaveError(errorMessage(err)))
          }}
        />
      )}
    </section>
  )
}
