import { useState } from 'react'
import { financeApi } from '../../api/finance.ts'
import type { CategoryTemplate } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

// Vorlagen für Kategorien (Konzept vereinskasse-steuern, S8): legt fehlende Kategorien eines
// Vereins (allgemein, Schützen, Sport, Musik) mit steuerlichem Bereich an, ändert nie bestehende.
// Ohne jede Kategorie steht die Vorlage gleich offen: Ohne Kategorien lässt sich nichts buchen.
export function CategoryTemplates({
  onApplied,
  startOpen = false,
}: {
  onApplied: () => Promise<unknown>
  startOpen?: boolean
}) {
  const org = useActiveOrg()
  const [open, setOpen] = useState(startOpen)
  const templates = useLoad(
    () => (open ? financeApi.categoryTemplates(org.id) : Promise.resolve(null)),
    [org.id, open],
  )
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)

  if (!open) {
    return (
      <p>
        <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
          {t('Vorlage übernehmen')}
        </button>
      </p>
    )
  }
  if (templates.error) return <Alert kind="error">{templates.error}</Alert>
  if (!templates.data) return <Loading />
  const list: CategoryTemplate[] = templates.data
  const chosen = list.find((x) => x.key === key) ?? list[0]
  const missing = chosen ? chosen.categories.filter((c) => !c.exists) : []

  async function apply() {
    if (!chosen) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await financeApi.applyCategoryTemplate(org.id, chosen.key)
      setMessage({
        kind: 'success',
        text: t('{n} Kategorien angelegt.', { n: result.created.length }),
      })
      await onApplied()
      await templates.reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="subcard" data-testid="category-templates">
      <h3>{t('Vorlage übernehmen')}</h3>
      <p className="muted small">
        {t(
          'Übliche Kategorien mit steuerlichem Bereich, damit ihr nicht bei null anfangt. Es werden nur fehlende Kategorien angelegt; bestehende bleiben, wie sie sind. Bereiche und DATEV-Konten bitte mit der Steuerberatung abstimmen. Sponsoring: Wird der Sponsor nur genannt, gehört das Geld zur Vermögensverwaltung; aktive Werbung wie Bande oder Anzeige ist wirtschaftlicher Geschäftsbetrieb.',
        )}
      </p>
      <label className="field">
        <span>{t('Vorlage')}</span>
        <select value={chosen?.key ?? ''} onChange={(e) => setKey(e.target.value)}>
          {list.map((x) => (
            <option key={x.key} value={x.key}>
              {x.label}
            </option>
          ))}
        </select>
      </label>
      {chosen && (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Kategorie')}</th>
              <th>{t('Art')}</th>
              <th>{t('Bereich')}</th>
            </tr>
          </thead>
          <tbody>
            {chosen.categories.map((c) => (
              <tr key={c.name} className={c.exists ? 'muted' : undefined}>
                <td>
                  {c.name}
                  {c.exists && <span className="muted small"> ({t('schon vorhanden')})</span>}
                </td>
                <td>{c.kind_label}</td>
                <td>{c.tax_area_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="actions">
        <button
          type="button"
          className="button"
          disabled={busy || missing.length === 0}
          onClick={() => void apply()}
        >
          {t('{n} Kategorien anlegen', { n: missing.length })}
        </button>
        <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
          {t('Schließen')}
        </button>
      </div>
    </div>
  )
}
