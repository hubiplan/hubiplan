// Mein Konto › Profil › Startseite: Schnellaktionen wieder zeigen oder den Vorschlag herstellen (S-04).
import { useState } from 'react'
import { homeActionsApi } from '../../api/homeActions.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { actionCatalog } from '../../components/home/roleActions.ts'
import type { HomeActionsUpdate } from '../../api/homeActions.ts'

/** Nur für Personen, die in einer Einheit Schnellaktionen bekommen können. */
export function HomeActionsCard() {
  const { orgs } = useOrg()
  if (!orgs.some((o) => actionCatalog(o).length > 0)) return null
  return <HomeActionsChoice />
}

function HomeActionsChoice() {
  const { data, setData } = useLoad(() => homeActionsApi.get(), [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!data) return null
  const hidden = data.hidden

  async function save(next: HomeActionsUpdate) {
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
  const own = Object.keys(data.chosen ?? {})
  return (
    <div className="card card-wide">
      <h2>{t('Startseite')}</h2>
      <Checkbox
        label={t('Schnellaktionen auf der Startseite zeigen')}
        checked={!hidden.includes('*')}
        busy={busy}
        onChange={(v) =>
          void save({ hidden: v ? hidden.filter((k) => k !== '*') : [...hidden, '*'] })
        }
        hint={t(
          'Welche Aktionen in welcher Reihenfolge erscheinen, wählst du auf der Startseite unter „Anpassen“.',
        )}
      />
      {single > 0 && (
        <p className="muted small">
          {t('{n} einzeln ausgeblendet.', { n: single })}{' '}
          <button
            type="button"
            className="link-button"
            disabled={busy}
            onClick={() => void save({ hidden: hidden.filter((k) => k === '*') })}
          >
            {t('Alle wieder zeigen')}
          </button>
        </p>
      )}
      {own.length > 0 && (
        <p className="muted small">
          {tn('Eigene Auswahl in einem Bereich.', 'Eigene Auswahl in {n} Bereichen.', own.length)}{' '}
          <button
            type="button"
            className="link-button"
            disabled={busy}
            onClick={() =>
              void save({ chosen: Object.fromEntries(own.map((scope) => [scope, null])) })
            }
          >
            {t('Überall den Vorschlag zeigen')}
          </button>
        </p>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
