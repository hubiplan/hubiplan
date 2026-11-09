// Mein Konto › Profil › Startseite: ausgeblendete Schnellaktionen wieder zeigen (S-04).
import { useState } from 'react'
import { homeActionsApi } from '../../api/homeActions.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { roleActionCandidates } from '../../components/home/roleActions.ts'

/** Nur für Personen, die in einer Einheit Schnellaktionen bekommen können. */
export function HomeActionsCard() {
  const { orgs } = useOrg()
  if (!orgs.some((o) => roleActionCandidates(o).length > 0)) return null
  return <HomeActionsChoice />
}

function HomeActionsChoice() {
  const { data, setData } = useLoad(() => homeActionsApi.get(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!data) return null
  const hidden = data.hidden

  async function save(next: string[]) {
    setBusy(true)
    setError(null)
    try {
      setData(await homeActionsApi.update(next))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const single = hidden.filter((k) => k !== '*').length
  return (
    <div className="card card-wide">
      <h2>{t('Startseite')}</h2>
      <Checkbox
        label={t('Schnellaktionen auf der Startseite zeigen')}
        checked={!hidden.includes('*')}
        busy={busy}
        onChange={(v) => void save(v ? hidden.filter((k) => k !== '*') : [...hidden, '*'])}
        hint={t('Einzelne Aktionen blendest du auf der Startseite unter „Anpassen“ aus.')}
      />
      {single > 0 && (
        <p className="muted small">
          {t('{n} einzeln ausgeblendet.', { n: single })}{' '}
          <button
            type="button"
            className="link-button"
            disabled={busy}
            onClick={() => void save(hidden.filter((k) => k === '*'))}
          >
            {t('Alle wieder zeigen')}
          </button>
        </p>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
