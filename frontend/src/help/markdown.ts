// Markdown der Hilfe in HTML: ohne rohes HTML, Bilder nur bild:name, Links nur eigene
// Seiten (/…) und Webadressen (neues Fenster).
import MarkdownIt from 'markdown-it'
import { lang } from '../i18n/index.ts'
import { IMAGE_PREFIX, imageUrl } from './content.ts'

const md = new MarkdownIt({ html: false, linkify: false, typographer: false })

md.renderer.rules.image = (tokens, idx) => {
  const token = tokens[idx]
  const src = String(token.attrGet('src') ?? '')
  const alt = md.utils.escapeHtml(token.content)
  if (!src.startsWith(IMAGE_PREFIX)) return ''
  const url = imageUrl(src.slice(IMAGE_PREFIX.length), lang())
  return `<img class="help-image" src="${md.utils.escapeHtml(url)}" alt="${alt}" loading="lazy">`
}

const defaultLink =
  md.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const href = String(tokens[idx].attrGet('href') ?? '')
  if (/^https?:\/\//.test(href)) {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noreferrer noopener')
  } else if (!href.startsWith('/')) {
    // Nur eigene Seiten und Webadressen
    tokens[idx].attrSet('href', '#')
  }
  return defaultLink(tokens, idx, options, env, self)
}

/** Markdown in HTML (für Tests und die Anzeige). */
export function renderHelp(body: string): string {
  return md.render(body)
}

export interface HelpSectionText {
  /** Überschrift ohne „## “ */
  title: string
  body: string
}

/**
 * Text an den Zwischenüberschriften („## …“) teilen: Einleitung und Abschnitte. Lange
 * Seitenhilfen zeigt die Leiste so eingeklappt, die Hilfe-Seite mit Inhaltsübersicht.
 */
export function splitSections(body: string): { lead: string; sections: HelpSectionText[] } {
  const lead: string[] = []
  const sections: HelpSectionText[] = []
  let fenced = false
  for (const line of body.split('\n')) {
    if (line.startsWith('```')) fenced = !fenced
    const m = fenced ? null : /^## +(.+?)\s*$/.exec(line)
    if (m) sections.push({ title: m[1], body: '' })
    else if (sections.length) sections[sections.length - 1].body += `${line}\n`
    else lead.push(line)
  }
  return {
    lead: lead.join('\n').trim(),
    sections: sections.map((x) => ({ ...x, body: x.body.trim() })),
  }
}

/** Anker eines Abschnitts auf der Hilfe-Seite, z. B. „abschnitt-gaeste-einladen“. */
export function sectionAnchor(title: string): string {
  const slug = title
    .toLocaleLowerCase()
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `abschnitt-${slug}`
}
