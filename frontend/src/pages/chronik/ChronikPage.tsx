// Verein › Chronik (Modul „Chronik“): Zeitleiste der Vereinsgeschichte pflegen, auch ohne
// Webseite. Gespeichert wird wie bisher als Textseite „Chronik“ der Webseite; mit Modul
// „Webseite“ erscheint die veröffentlichte Fassung dort.
import { Link } from 'react-router-dom'
import { chronicleApi } from '../../api/website.ts'
import type { TimelineEntry } from '../../api/website.ts'
import { PERM } from '../../api/orgs.ts'
import { useLoad } from '../../components/forms.ts'
import { Alert, LoadError } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { TextPanel } from '../website/ContentPage.tsx'
import { periodLabel, sortTimeline } from '../website/timeline.ts'

export function ChronikPage() {
  const org = useActiveOrg()
  const allowed = org.modules.includes('chronicle') && org.permissions.includes(PERM.chronicleView)
  const { data, error, reload } = useLoad(
    () => (allowed ? chronicleApi.get(org.id) : Promise.resolve(null)),
    [org.id, allowed],
  )
  if (!allowed) return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <p className="muted">{t('Lädt …')}</p>
  const hint = data.website ? (
    <p className="muted small">
      {t('Veröffentlicht erscheint die Chronik auf der Webseite.')}{' '}
      {org.permissions.includes(PERM.websiteContent) && (
        <Link to="/webseite/inhalte">{t('Zur Webseite')}</Link>
      )}
    </p>
  ) : (
    <p className="muted small">
      {t(
        'Die Chronik ist Vereinswissen, etwa für Festschrift und Jubiläum. Mit dem Modul „Webseite“ erscheint die veröffentlichte Fassung auch dort.',
      )}
    </p>
  )
  if (!data.text) {
    return (
      <div className="stack">
        {hint}
        <Alert kind="info">{t('Noch keine Chronik angelegt.')}</Alert>
      </div>
    )
  }
  if (!data.can_edit) {
    return (
      <div className="stack">
        {hint}
        <ReadOnlyTimeline entries={data.text.timeline ?? []} />
      </div>
    )
  }
  return (
    <div className="stack">
      {hint}
      <TextPanel
        id={data.text.id}
        units={[]}
        linkTargets={[]}
        chronicle
        onChanged={() => undefined}
        onDeleted={() => void reload()}
      />
    </div>
  )
}

function ReadOnlyTimeline({ entries }: { entries: TimelineEntry[] }) {
  if (!entries.length) return <p className="muted">{t('Die Zeitleiste ist noch leer.')}</p>
  return (
    <ul className="plain-list">
      {sortTimeline(entries).map((e, i) =>
        e.kind === 'chapter' ? (
          <li key={i}>
            <h3>{e.title}</h3>
          </li>
        ) : (
          <li key={i}>
            <strong>{periodLabel(e)}</strong> {e.title}
            {e.text && <p className="muted small">{e.text}</p>}
          </li>
        ),
      )}
    </ul>
  )
}
