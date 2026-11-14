// Verweise auseinanderhalten (Ralf 14.11.2026, Termin › „Zu diesem Termin“): Zwei Textverweise
// direkt hintereinander lesen sich wie ein einziger Satz; man sieht weder, dass es zwei Ziele
// sind, noch, welches nur anzeigt und welches etwas anlegt. Der Test sucht Stellen, an denen
// zwei schlichte Textverweise (Link, NavLink, a ohne className) unmittelbar aufeinander folgen,
// nur durch Leerraum getrennt. Verweise mit eigener Klasse (Knopf, Kachel, link-button) sehen
// schon für sich abgegrenzt aus; eine Navigationsleiste (<nav>, z. B. Fußzeile) ist als Reihe
// gleichrangiger Ziele gemeint. Abhilfe: Die Aktion (anlegen, öffnen, herunterladen …) wird ein Knopf
// (`className="button …"`, beim Anlegen mit „+“), oder die Verweise kommen in eine Liste bzw.
// werden durch Text („·“, „oder“) getrennt.
import { parseAst } from 'rolldown/parseAst'
import { describe, expect, it } from 'vitest'

const seiten = import.meta.glob(['../**/*.tsx', '!../test/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

type Knoten = { type: string; [k: string]: unknown }

const VERWEISE = new Set(['Link', 'NavLink', 'a'])

function tagName(el: Knoten): string {
  const name = (el.openingElement as { name: Knoten }).name
  return name.type === 'JSXIdentifier' ? (name.name as string) : '?'
}

function hatKlasse(el: Knoten): boolean {
  const attribute = (el.openingElement as { attributes: Knoten[] }).attributes
  return attribute.some((a) => a.type === 'JSXAttribute' && (a.name as Knoten).name === 'className')
}

/** Ein Kind als Platz: Textverweis, Trenner oder nichts (Leerraum, Kommentar). */
function platz(kind: Knoten): 'verweis' | 'anderes' | null {
  if (kind.type === 'JSXText') return (kind.value as string).trim() ? 'anderes' : null
  if (kind.type === 'JSXElement') {
    return VERWEISE.has(tagName(kind)) && !hatKlasse(kind) ? 'verweis' : 'anderes'
  }
  if (kind.type === 'JSXExpressionContainer') {
    let e = kind.expression as Knoten
    if (e.type === 'JSXEmptyExpression') return null
    if (e.type === 'Literal' && typeof e.value === 'string' && !e.value.trim()) return null
    if (e.type === 'LogicalExpression') e = e.right as Knoten
    if (e.type === 'ParenthesizedExpression') e = e.expression as Knoten
    if (e.type === 'JSXElement') return platz(e)
    return 'anderes'
  }
  return 'anderes'
}

function zeile(quelle: string, pos: number): number {
  return quelle.slice(0, pos).split('\n').length
}

function verweisPaare(): string[] {
  const funde: string[] = []
  for (const [datei, quelle] of Object.entries(seiten)) {
    const ast = parseAst(quelle, { lang: 'tsx' }, datei) as unknown as Knoten
    const besuche = (n: unknown): void => {
      if (!n || typeof n !== 'object') return
      const k = n as Knoten
      if ((k.type === 'JSXElement' && tagName(k) !== 'nav') || k.type === 'JSXFragment') {
        const kinder = k.children as Knoten[]
        let vorher: Knoten | null = null
        for (const kind of kinder) {
          const p = platz(kind)
          if (p === null) continue
          if (p === 'verweis' && vorher)
            funde.push(`${datei.replace('../', 'src/')}:${zeile(quelle, kind.start as number)}`)
          vorher = p === 'verweis' ? kind : null
        }
      }
      for (const v of Object.values(k)) {
        if (Array.isArray(v)) v.forEach(besuche)
        else if (v && typeof v === 'object') besuche(v)
      }
    }
    besuche(ast)
  }
  return funde.sort()
}

describe('Verweise nebeneinander', () => {
  it('stellt nie zwei Textverweise unmittelbar hintereinander', () => {
    expect(verweisPaare()).toEqual([])
  })
})
