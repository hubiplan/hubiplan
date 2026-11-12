// Knopfabstand (Ralf 25.10. und 11.11.2026, Rechnungspostfach): Knöpfe stehen nie ohne Abstand
// neben- oder untereinander. jsdom rechnet kein Layout; der Test liest deshalb alle Seiten und
// sucht Stellen, an denen zwei Knöpfe direkt aufeinander folgen. Ihr gemeinsamer Container
// braucht dann einen Abstand: eine Klasse, die in einer CSS-Datei `gap` bekommt (z. B.
// .button-row, .actions, .stack), oder ein Textelement (li, p, dd, td, th), in dem index.css
// Knöpfen zentral Rand gibt. Bewusst verbundene Segmentknöpfe stehen in VERBUNDEN.
// Parser: rolldown kommt mit Vite 8 und liest TSX ohne weitere Abhängigkeit.
import { parseAst } from 'rolldown/parseAst'
import { describe, expect, it } from 'vitest'

const seiten = import.meta.glob(['../**/*.tsx', '!../test/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const stile = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Segmentschalter: Knöpfe teilen sich absichtlich einen gemeinsamen Rahmen. */
const VERBUNDEN = new Set(['segmented', 'style-segments'])
/** Textelemente, in denen index.css Knöpfen Rand gibt (`:where(li, p, dd, td, th) > .button`). */
const TEXTELEMENTE = new Set(['li', 'p', 'dd', 'td', 'th'])
/** In solchen Containern nimmt index.css den Rand der Knöpfe wieder weg; dort zählt nur gap. */
const NUR_GAP = /row|toolbar|-actions|-head|-tools|-filters|^stack|^filters$/

type Knoten = { type: string; [k: string]: unknown }

function teileOberste(selektor: string): string[] {
  const teile: string[] = []
  let tiefe = 0
  let aktuell = ''
  for (const z of selektor) {
    if (z === '(') tiefe++
    if (z === ')') tiefe--
    if (z === ',' && tiefe === 0) {
      teile.push(aktuell)
      aktuell = ''
    } else aktuell += z
  }
  teile.push(aktuell)
  return teile
}

/** Klassen, die als eigener Selektor (ohne Vorfahren) einen `gap` bekommen. */
function gapKlassen(): Set<string> {
  const klassen = new Set<string>()
  for (const css of Object.values(stile)) {
    const ohneKommentare = css.replace(/\/\*[\s\S]*?\*\//g, '')
    for (const m of ohneKommentare.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!/(^|[;\s])gap\s*:/.test(m[2])) continue
      for (let teil of teileOberste(m[1].trim())) {
        teil = teil.trim().replace(/^:where\(([^()]*)\)$/, '$1')
        if (/[\s>+~]/.test(teil.replace(/\([^()]*\)/g, ''))) continue
        for (const k of teil.replace(/:not\([^()]*\)/g, '').match(/\.[\w-]+/g) ?? [])
          klassen.add(k.slice(1))
      }
    }
  }
  return klassen
}

function tagName(el: Knoten): string {
  const name = (el.openingElement as { name: Knoten }).name
  if (name.type === 'JSXIdentifier') return name.name as string
  if (name.type === 'JSXMemberExpression') return 'Member'
  return '?'
}

/** Alle festen Textteile des className-Ausdrucks (Literal, Template, cx(...)). */
function klassen(el: Knoten): string[] | null {
  const attribute = (el.openingElement as { attributes: Knoten[] }).attributes
  const attr = attribute.find(
    (a) => a.type === 'JSXAttribute' && (a.name as Knoten).name === 'className',
  )
  if (!attr) return null
  const teile: string[] = []
  const sammle = (n: unknown): void => {
    if (!n || typeof n !== 'object') return
    const k = n as Knoten
    if (k.type === 'Literal' && typeof k.value === 'string') teile.push(k.value)
    if (k.type === 'TemplateElement') teile.push((k.value as { cooked: string }).cooked)
    for (const v of Object.values(k)) {
      if (Array.isArray(v)) v.forEach(sammle)
      else if (v && typeof v === 'object') sammle(v)
    }
  }
  sammle(attr.value)
  return teile.join(' ').split(/\s+/).filter(Boolean)
}

function istKnopf(el: Knoten): boolean {
  const k = klassen(el)
  if (k?.includes('button-block')) return false // eigene Zeile mit Rand oben
  if (k?.includes('button')) return true
  return tagName(el) === 'button' && k === null
}

/** Kinder in Darstellungsreihenfolge; ein Platz ist ein Knopf, wenn er einer sein kann. */
function plaetze(kinder: Knoten[]): ('knopf' | 'anderes')[] {
  const ergebnis: ('knopf' | 'anderes')[] = []
  const ausdruck = (e: Knoten | null): boolean | null => {
    if (!e) return null
    switch (e.type) {
      case 'ParenthesizedExpression':
        return ausdruck(e.expression as Knoten)
      case 'LogicalExpression':
        return ausdruck(e.right as Knoten)
      case 'ConditionalExpression': {
        const a = ausdruck(e.consequent as Knoten)
        const b = ausdruck(e.alternate as Knoten)
        if (a === null && b === null) return null
        return !!a || !!b
      }
      case 'JSXElement':
        return istKnopf(e)
      case 'JSXFragment': {
        const innen = plaetze(e.children as Knoten[])
        ergebnis.push(...innen)
        return null
      }
      case 'CallExpression': {
        const callee = e.callee as Knoten
        if (callee.type === 'MemberExpression' && (callee.property as Knoten).name === 'map') {
          const fn = (e.arguments as Knoten[])[0]
          if (fn?.type === 'ArrowFunctionExpression' && fn.body) {
            const body = fn.body as Knoten
            let wert: boolean | null = null
            if (body.type === 'BlockStatement') {
              for (const s of body.body as Knoten[])
                if (s.type === 'ReturnStatement') wert = ausdruck(s.argument as Knoten) ?? wert
            } else wert = ausdruck(body)
            if (wert) {
              ergebnis.push('knopf', 'knopf')
              return null
            }
            return wert === null ? null : false
          }
        }
        return false
      }
      case 'Literal':
      case 'TemplateLiteral':
        return false
      default:
        return false
    }
  }
  for (const kind of kinder) {
    if (kind.type === 'JSXText') {
      const text = kind.value as string
      if (text.trim() || !text.includes('\n')) ergebnis.push('anderes')
      continue
    }
    if (kind.type === 'JSXElement') {
      ergebnis.push(istKnopf(kind) ? 'knopf' : 'anderes')
      continue
    }
    if (kind.type === 'JSXFragment') {
      ergebnis.push(...plaetze(kind.children as Knoten[]))
      continue
    }
    if (kind.type === 'JSXExpressionContainer') {
      const e = kind.expression as Knoten
      if (e.type === 'JSXEmptyExpression') continue
      const wert = ausdruck(e)
      if (wert !== null) ergebnis.push(wert ? 'knopf' : 'anderes')
    }
  }
  return ergebnis
}

function zeile(quelle: string, pos: number): number {
  return quelle.slice(0, pos).split('\n').length
}

function knopfPaareOhneAbstand(): string[] {
  const gap = gapKlassen()
  const funde: string[] = []
  for (const [datei, quelle] of Object.entries(seiten)) {
    const ast = parseAst(quelle, { lang: 'tsx' }, datei) as unknown as Knoten
    const besuche = (n: unknown): void => {
      if (!n || typeof n !== 'object') return
      const k = n as Knoten
      if (k.type === 'JSXElement') {
        const p = plaetze(k.children as Knoten[])
        const nebeneinander = p.some((x, i) => x === 'knopf' && p[i + 1] === 'knopf')
        if (nebeneinander) {
          const tag = tagName(k)
          const kl = klassen(k) ?? []
          const ok =
            kl.some((c) => gap.has(c) || VERBUNDEN.has(c)) ||
            (TEXTELEMENTE.has(tag) && !kl.some((c) => NUR_GAP.test(c)))
          if (!ok)
            funde.push(
              `${datei.replace('../', 'src/')}:${zeile(quelle, k.start as number)} <${tag}${
                kl.length ? ` class="${kl.join(' ')}"` : ''
              }>`,
            )
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

describe('Knopfabstand', () => {
  it('erkennt gap-Container aus den Stylesheets', () => {
    const gap = gapKlassen()
    for (const k of ['button-row', 'actions', 'stack', 'card-head']) expect(gap).toContain(k)
  })

  it('setzt nebeneinanderstehende Knöpfe immer in einen Container mit Abstand', () => {
    expect(knopfPaareOhneAbstand()).toEqual([])
  })
})
