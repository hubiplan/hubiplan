// Einstellungen › Einrichtung (Übersicht), Konzept S-02: alle Einrichtungspunkte der aktiven
// Module mit Stand, Suche und Fortschritt über die Pflichtpunkte. Jede Zeile führt auf die
// bestehende Seite im Modul; nichts wird verschoben.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { orgApi } from '../../api/orgs.ts'
import type { SetupStatus } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { baseSettingsItems } from './items.ts'
import { setupGroups } from './setup.ts'
import { t } from '../../i18n/index.ts'

function statusText(s: SetupStatus | undefined): {
  text: string
  tone: 'ok' | 'missing' | 'muted'
} {
  if (!s) return { text: '', tone: 'muted' }
  if (s.count !== undefined) {
    const text = t('{n} angelegt', { n: s.count })
    if (s.done) return { text, tone: 'ok' }
    return s.required
      ? { text, tone: 'missing' }
      : { text: t('optional · {n}', { n: s.count }), tone: 'muted' }
  }
  if (s.done) return { text: t('ausgefüllt'), tone: 'ok' }
  return s.required
    ? { text: t('Angaben fehlen'), tone: 'missing' }
    : { text: t('optional'), tone: 'muted' }
}

export function SetupOverviewPage() {
  const org = useActiveOrg()
  const groups = setupGroups(org, baseSettingsItems(org))
  const status = useLoad(() => orgApi.setupStatus(org.id), [org.id])
  const [query, setQuery] = useState('')
  const items = status.data?.items ?? {}
  const visible = new Set(groups.flatMap((g) => g.items.map((i) => i.to)))
  const required = Object.entries(items).filter(([to, s]) => s.required && visible.has(to))
  const done = required.filter(([, s]) => s.done).length
  const q = query.trim().toLocaleLowerCase()
  const shown = groups
    .map((g) => ({
      ...g,
      items: q
        ? g.items.filter((i) => `${g.label} ${i.label}`.toLocaleLowerCase().includes(q))
        : g.items,
    }))
    .filter((g) => g.items.length > 0)
  return (
    <div className="setup-overview">
      <p className="muted">
        {t(
          'Alle Einrichtungsseiten der eingeschalteten Module an einem Ort. Die Seiten selbst bleiben in ihrem Bereich.',
        )}{' '}
        {status.data && required.length > 0 && (
          <strong>
            {t('{done} von {total} Pflichtpunkten erledigt', { done, total: required.length })}
          </strong>
        )}
      </p>
      {status.data && required.length > 0 && (
        <progress
          className="setup-progress"
          max={required.length}
          value={done}
          aria-label={t('Fortschritt der Einrichtung')}
        />
      )}
      <input
        type="search"
        className="search-input"
        placeholder={t('Einrichtung suchen …')}
        aria-label={t('Einrichtung suchen')}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {status.error && (
        <LoadError
          message={t('Der Stand der Einrichtung ließ sich nicht laden.')}
          onRetry={status.reload}
        />
      )}
      {shown.length === 0 && (
        <p className="muted">{t('Kein Einrichtungspunkt passt zur Suche.')}</p>
      )}
      {shown.map((g) => (
        <section key={g.key} className="setup-group" aria-labelledby={`setup-${g.key}`}>
          <h2 id={`setup-${g.key}`} className="section-heading">
            {g.label}
          </h2>
          <ul className="plain-list setup-list">
            {g.items.map((i) => {
              const s = items[i.to]
              const st = statusText(s)
              return (
                <li key={i.to}>
                  <Link to={i.to} className="setup-row">
                    <span className="setup-label">{i.label}</span>
                    {st.text && (
                      <span className={`setup-status setup-status-${st.tone}`}>
                        {st.tone === 'ok' && <span aria-hidden="true">✓ </span>}
                        {st.text}
                        {s?.missing && s.missing.length > 0 && !s.done && (
                          <>: {s.missing.join(', ')}</>
                        )}
                      </span>
                    )}
                  </Link>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
