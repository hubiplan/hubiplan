// Text einer Hilfedatei anzeigen. Nur eigene Texte aus dem Repo, trotzdem ohne rohes HTML.
// Interne Links (/mitglieder) wechseln die Seite ohne Neuladen; Bilder kommen aus
// /hilfe-bilder/<sprache>/ (scripts/hilfe-bilder.sh).
import { useMemo } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { fillTerms, useTerms } from '../org/terms.ts'
import { t } from '../i18n/index.ts'
import { renderHelp, sectionAnchor, splitSections } from './markdown.ts'

export function HelpMarkdown({ body, onNavigate }: { body: string; onNavigate?: () => void }) {
  const terms = useTerms()
  const navigate = useNavigate()
  const html = useMemo(() => renderHelp(fillTerms(body, terms)), [body, terms])
  const click = (e: MouseEvent<HTMLDivElement>) => {
    const a = (e.target as HTMLElement).closest('a')
    const href = a?.getAttribute('href')
    if (!a || !href?.startsWith('/') || e.metaKey || e.ctrlKey || e.shiftKey) return
    e.preventDefault()
    navigate(href)
    onNavigate?.()
  }
  return (
    // Klicks auf Links im Text; die Links selbst sind per Tastatur erreichbar
    // oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div className="help-text" onClick={click} dangerouslySetInnerHTML={{ __html: html }} />
  )
}

/**
 * Text mit Zwischenüberschriften. In der Leiste (`collapsed`) steht die Einleitung offen und
 * jeder Abschnitt eingeklappt; auf der Hilfe-Seite stehen alle offen, ab drei Abschnitten mit
 * einer Inhaltsübersicht davor. `between` erscheint nach der Einleitung (Leiste: Aufgaben).
 */
export function HelpSections({
  body,
  collapsed = false,
  onNavigate,
  between,
}: {
  body: string
  collapsed?: boolean
  onNavigate?: () => void
  between?: ReactNode
}) {
  const { lead, sections } = useMemo(() => splitSections(body), [body])
  if (sections.length === 0)
    return (
      <>
        <HelpMarkdown body={body} onNavigate={onNavigate} />
        {between}
      </>
    )
  return (
    <>
      {lead && <HelpMarkdown body={lead} onNavigate={onNavigate} />}
      {between}
      {!collapsed && sections.length >= 3 && (
        <nav className="help-toc" aria-label={t('Auf dieser Seite')}>
          <p className="help-toc-title">{t('Auf dieser Seite')}</p>
          <ul>
            {sections.map((x) => (
              <li key={x.title}>
                <a href={`#${sectionAnchor(x.title)}`}>{x.title}</a>
              </li>
            ))}
          </ul>
        </nav>
      )}
      {collapsed ? (
        <div className="help-sections">
          {sections.map((x) => (
            <details key={x.title} className="help-section">
              <summary>{x.title}</summary>
              <HelpMarkdown body={x.body} onNavigate={onNavigate} />
            </details>
          ))}
        </div>
      ) : (
        sections.map((x) => (
          <section key={x.title} id={sectionAnchor(x.title)} className="help-section-open">
            <h2>{x.title}</h2>
            <HelpMarkdown body={x.body} onNavigate={onNavigate} />
          </section>
        ))
      )}
    </>
  )
}
