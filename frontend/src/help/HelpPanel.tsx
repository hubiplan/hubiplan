// Seitenhilfe: Leiste rechts (schmal: Blatt von unten) mit der Hilfe zur aktuellen Seite.
// Bleibt beim Seitenwechsel offen und zeigt dann die Hilfe der neuen Seite.
import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { t } from '../i18n/index.ts'
import { TERMS, termAnchor, tr } from '../learning/content.ts'
import type { TermKey } from '../learning/content.ts'
import { useLearning } from '../learning/LearningContext.tsx'
import { useOptionalOrg } from '../org/OrgContext.tsx'
import { guidesFor, pageHelpFor, routeMatches } from './content.ts'
import type { HelpEntry } from './content.ts'
import { useHelp } from './HelpContext.tsx'
import type { HelpState } from './HelpContext.tsx'
import { BlockedGuide, GuideNotes, HelpContacts, ShowMe } from './HelpExtras.tsx'
import { HelpMarkdown } from './HelpMarkdown.tsx'
import { itemLabel, placeOf } from './menu.ts'
import './help.css'

/** Höchstens so viele Begriffe zeigt die Leiste zu einer Seite. */
const MAX_TERMS = 6

/** Begriffe aus dem Glossar, die im Text der Seitenhilfe vorkommen (ganzes Wort). */
// oxlint-disable-next-line react/only-export-components
export function termsIn(
  entry: Pick<HelpEntry, 'body'>,
  has: (feature: (typeof TERMS)[TermKey]['feature']) => boolean,
): TermKey[] {
  const text = entry.body.toLocaleLowerCase()
  return (Object.keys(TERMS) as TermKey[])
    .filter((k) => has(TERMS[k].feature))
    .filter((k) => {
      const name = tr(TERMS[k].name).toLocaleLowerCase()
      const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      return name.length > 2 && new RegExp(`(^|[^\\p{L}])${escaped}($|[^\\p{L}])`, 'u').test(text)
    })
    .slice(0, MAX_TERMS)
}

export function HelpButton() {
  const help = useHelp()
  if (!help) return null
  return (
    <button
      type="button"
      className="button button-ghost help-button"
      aria-label={t('Hilfe zu dieser Seite')}
      title={t('Hilfe zu dieser Seite')}
      aria-expanded={help.panelOpen}
      aria-controls="seitenhilfe"
      aria-keyshortcuts="?"
      onClick={() => help.setPanelOpen(!help.panelOpen)}
    >
      <span aria-hidden="true" className="help-button-mark">
        ?
      </span>
      {/* W-07: sichtbar wie der Name, damit „Hilfe“ nur die Hilfe-Seite in der Seitenleiste meint */}
      <span className="help-button-label">{t('Hilfe zu dieser Seite')}</span>
    </button>
  )
}

export function HelpPanel() {
  const help = useHelp()
  // Eigene Komponente für die offene Leiste: jedes Öffnen beginnt mit der Seitenübersicht
  return help?.panelOpen ? <OpenHelpPanel help={help} /> : null
}

const ALL = () => true

function OpenHelpPanel({ help }: { help: HelpState }) {
  const { pathname } = useLocation()
  const hasFeature = useLearning()?.hasFeature ?? ALL
  const org = useOptionalOrg()?.active ?? null
  // Gewählte Anleitung gilt nur auf der Seite, auf der sie gewählt wurde
  const chosen = help.panelGuide
  const setChosen = help.openGuide
  const headingRef = useRef<HTMLHeadingElement>(null)
  const { setPanelOpen } = help

  // Fokus in die Leiste, beim Schließen zurück; Esc schließt auch ohne Fokus in der Leiste
  useEffect(() => {
    const opener = document.activeElement
    headingRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      // Offene Dialoge schließen zuerst sich selbst
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return
      setPanelOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus()
    }
  }, [setPanelOpen])
  // Nach Wahl einer Anleitung den Fokus auf ihren Titel
  useEffect(() => {
    if (chosen) headingRef.current?.focus()
  }, [chosen])

  const close = () => help.setPanelOpen(false)
  const all = help.entries?.filter(help.visible) ?? []
  const page = pageHelpFor(all, pathname)
  const guides = guidesFor(all, pathname)
  // Anleitungen zu dieser Seite, für die ein Recht fehlt (ausgegraut, F1)
  const blocked = (help.entries ?? []).filter(
    (e) =>
      e.kind === 'guide' &&
      help.missing(e).length > 0 &&
      e.routes.some((r) => routeMatches(r, pathname)),
  )
  const terms = page ? termsIn(page, hasFeature) : []
  const place = page ? placeOf(page) : null
  const guideKey = chosen?.path === pathname ? chosen.key : null
  const guide = guideKey ? all.find((e) => e.key === guideKey) : undefined

  return (
    <aside id="seitenhilfe" className="help-panel" aria-labelledby="seitenhilfe-titel">
      <div className="help-panel-head">
        <h2 id="seitenhilfe-titel" tabIndex={-1} ref={headingRef}>
          {guide ? guide.title : t('Hilfe zu dieser Seite')}
        </h2>
        <button type="button" className="button button-ghost" onClick={close}>
          <span aria-hidden="true">×</span> {t('Hilfe schließen')}
        </button>
      </div>
      {help.failed && (
        <p role="alert">
          {t('Die Hilfe konnte nicht geladen werden.')}{' '}
          <button type="button" className="link-button" onClick={help.load}>
            {t('Erneut versuchen')}
          </button>
        </p>
      )}
      {!help.entries && !help.failed && (
        <p className="muted" role="status">
          {t('Wird geladen …')}
        </p>
      )}
      {help.entries && guide && (
        <>
          <button type="button" className="link-button" onClick={() => setChosen(null)}>
            ← {t('Zurück zur Seite')}
          </button>
          <HelpMarkdown body={guide.body} />
          <ShowMe entry={guide} />
          <GuideNotes entry={guide} />
        </>
      )}
      {help.entries && !guide && (
        <>
          {page ? (
            <section aria-label={page.title}>
              <h3>{page.title}</h3>
              <HelpMarkdown body={page.body} />
            </section>
          ) : (
            <p className="muted">{t('Zu dieser Seite gibt es noch keine eigene Hilfe.')}</p>
          )}
          {guides.length + blocked.length > 0 && (
            <section>
              <h3>{t('Häufige Aufgaben')}</h3>
              <ul className="help-list">
                {guides.map((g) => (
                  <li key={g.key}>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setChosen({ key: g.key, path: pathname })}
                    >
                      {g.title}
                    </button>
                  </li>
                ))}
                {blocked.map((g) => (
                  <BlockedGuide key={g.key} entry={g} />
                ))}
              </ul>
            </section>
          )}
          {terms.length > 0 && (
            <section>
              <h3>{t('Begriffe auf dieser Seite')}</h3>
              <ul className="help-list">
                {terms.map((k) => (
                  <li key={k}>
                    <Link to={`/hilfe/begriffe#${termAnchor(k)}`} onClick={close}>
                      {tr(TERMS[k].name)}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
      {help.entries && !guide && <HelpContacts compact />}
      <p className="help-panel-foot">
        {place && (
          <>
            <Link to={`/hilfe/seiten#hilfe-${place.item}`} onClick={close}>
              {t('Mehr zu {x}', { x: itemLabel(place.item, org) })}
            </Link>
            {' · '}
          </>
        )}
        <Link to="/hilfe" onClick={close}>
          {t('Alle Hilfe und Glossar')}
        </Link>
      </p>
    </aside>
  )
}
