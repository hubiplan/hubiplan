// Verständliche Hinweise statt stiller Umleitung auf die Startseite.
import { Link } from 'react-router-dom'
import { displayName } from '../api/orgs.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { useOrg } from '../org/OrgContext.tsx'
import { usePageTitle } from '../components/pageTitle.ts'
import { t } from '../i18n/index.ts'
import { AppOpenLink } from '../components/AppOpenLink.tsx'

/**
 * Eine Karte für jeden Fall von „kein Zugriff“ (UX-Audit 16.11. VW-09, VW-35): fehlendes Recht,
 * ausgeschaltetes Modul oder falscher Arbeitsbereich, immer mit Überschrift und Ausweg.
 * `embedded`: innerhalb einer Seite mit eigenem Kopf (Überschrift zweiter Ebene, Titel bleibt).
 */
export function NoAccessPage({
  reason,
  embedded = false,
  need,
}: {
  reason: 'right' | 'workspace'
  embedded?: boolean
  /**
   * Was die Seite braucht. Damit bietet die Karte den Wechsel in die Einheiten an, in denen die
   * Person die Seite öffnen darf (UX-Audit 16.11. VW-10).
   */
  need?: { kind: 'org'; allows: (org: OrgSummary) => boolean } | { kind: 'dept' }
}) {
  usePageTitle(embedded ? null : t('Kein Zugriff'))
  const Heading = embedded ? 'h2' : 'h1'
  const { active, activeDept, activePortal, orgs, departments, select } = useOrg()
  const targets: { key: string; name: string }[] = !need
    ? []
    : need.kind === 'dept'
      ? departments
          .filter((d) => d.id !== activeDept?.id)
          .map((d) => ({ key: `d:${d.id}`, name: displayName(d) }))
      : orgs
          .filter((o) => o.id !== active?.id && need.allows(o))
          .map((o) => ({ key: String(o.id), name: displayName(o) }))
  const current = active
    ? displayName(active)
    : activeDept
      ? displayName(activeDept)
      : activePortal
        ? t('Meine Daten ({x})', { x: activePortal.club_display_name || activePortal.club_name })
        : null
  return (
    <section className="card" data-testid="kein-zugriff">
      <Heading>{t('Kein Zugriff in dieser Einheit')}</Heading>
      <p>
        {reason === 'right'
          ? t('Für diese Seite fehlt dir in der gewählten Einheit das nötige Recht.')
          : t('Diese Seite gehört zu einer anderen Einheit.')}
        {current && t(' Aktuell gewählt: {current}.', { current })}
      </p>
      <p className="muted">
        {targets.length > 0
          ? t('In diesen Einheiten darfst du die Seite öffnen:')
          : t(
              'Falls du in mehreren Einheiten arbeitest, wechsle oben rechts die Einheit. Sonst hilft dir weiter, wer bei euch die Konten verwaltet.',
            )}
      </p>
      <div className="button-row">
        {targets.slice(0, 8).map((x, i) => (
          <button
            key={x.key}
            type="button"
            className={i === 0 ? 'button button-primary' : 'button'}
            onClick={() => select(x.key)}
          >
            {t('Weiter in {x}', { x: x.name })}
          </button>
        ))}
        <Link to="/" className={targets.length > 0 ? 'button' : 'button button-primary'}>
          {t('Zur Startseite')}
        </Link>
      </div>
    </section>
  )
}

export function NotFoundPage() {
  usePageTitle(t('Seite nicht gefunden'))
  return (
    <section className="card">
      <h1>{t('Seite nicht gefunden')}</h1>
      <p>{t('Diese Adresse gibt es nicht (mehr). Vielleicht ist der Link veraltet.')}</p>
      <div className="button-row">
        <Link to="/" className="button button-primary">
          {t('Zur Startseite')}
        </Link>
      </div>
    </section>
  )
}

/**
 * Unbekannter oder nicht erlaubter Unterpfad eines Bereichs (alter Link, fehlendes Recht):
 * Hinweis und Weg zurück statt leerer Seite (UX-Audit 31.10. W07).
 */
export function SubpageUnavailable({ to, label }: { to: string; label: string }) {
  return (
    <div className="card">
      <p>
        {t(
          'Diese Ansicht gibt es nicht oder sie ist in deiner Einheit nicht verfügbar, z. B. weil das Recht dafür fehlt oder der Link veraltet ist.',
        )}
      </p>
      <div className="button-row">
        <Link to={to} className="button button-primary">
          {label}
        </Link>
      </div>
    </div>
  )
}

// Ziel des QR-Codes „App verbinden“, wenn ihn die normale Kamera statt der App öffnet.
// Der Code steht im Fragment (#) und wird hier weder angezeigt noch gesendet.
export function AppPairNoticePage() {
  usePageTitle(t('App verbinden'))
  return (
    <section className="card">
      <h1>{t('App verbinden')}</h1>
      <p>
        {t(
          'Dieser QR-Code verbindet die HUBIplan-App mit deinem Konto. Ist die App auf diesem Telefon installiert, tippe auf den Knopf. Sonst öffne die App, tippe auf „Mit QR-Code verbinden“ und scanne den Code dort.',
        )}
      </p>
      {/* X-04: derselbe Einmalcode wie im QR-Code (aus dem Fragment, nie an den Server) */}
      <AppOpenLink pairUrl={window.location.href} />
      <p className="muted">
        {t(
          'Der Code gilt nur kurz und nur einmal. Falls er abgelaufen ist, erzeugst du unter „Mein Konto“ einen neuen.',
        )}
      </p>
    </section>
  )
}
