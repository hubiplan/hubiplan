// Beschriftung über dem Feld (Ralf 14.11.2026, Versammlungen › Angaben und Tagesordnung): Ein
// `<label>` ohne Klasse mit Text und Textfeld, Auswahlliste oder Textbereich bekommt keine
// Regel aus index.css. Der Text klebt dann links am Feld, das Feld behält die schmale
// Browserbreite, und nichts fluchtet. Felder folgen deshalb dem gemeinsamen Muster
// `<label className="field"><span>Beschriftung</span><input … /></label>`.
// Ausnahmen: Bereiche mit eigener Regel für Beschriftungen (eine CSS-Regel `.bereich label`,
// dazu Musik und Material, deren Bereichsklasse in einer anderen Datei sitzt), Leisten mit
// Filtern (dort steht die Beschriftung bewusst neben dem Feld) und versteckte Beschriftungen.
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

/** Klassen, unter denen eine CSS-Regel Beschriftungen selbst gestaltet (`.bereich label`) */
function eigeneLabelRegeln(): Set<string> {
  const klassen = new Set<string>()
  for (const css of Object.values(stile)) {
    const ohneKommentare = css.replace(/\/\*[\s\S]*?\*\//g, '')
    for (const m of ohneKommentare.matchAll(/([^{}]+)\{/g))
      for (const teil of m[1].split(','))
        for (const k of teil.matchAll(/\.([\w-]+)[^.]*?\slabel\b/g)) klassen.add(k[1])
  }
  return klassen
}

/** Bereiche mit eigener Regel für `label` (music.css, materials.css) */
const EIGENE_REGEL = /^\.\.\/pages\/(music|materials)\//
/** Vorfahren, in denen eine Beschriftung neben dem Feld gewollt ist */
const NEBENEINANDER = /filters|toolbar|sr-only/
const KEIN_TEXTFELD = new Set(['checkbox', 'radio', 'file', 'hidden'])

type Knoten = { type: string; [k: string]: unknown }

function tagName(el: Knoten): string {
  const name = (el.openingElement as { name: Knoten }).name
  return name.type === 'JSXIdentifier' ? (name.name as string) : '?'
}

function attribut(el: Knoten, name: string): Knoten | undefined {
  return (el.openingElement as { attributes: Knoten[] }).attributes.find(
    (a) => a.type === 'JSXAttribute' && (a.name as Knoten).name === name,
  )
}

/** Feste Textteile des className-Ausdrucks */
function klassen(el: Knoten): string {
  const attr = attribut(el, 'className')
  if (!attr) return ''
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
  return teile.join(' ')
}

function istTextfeld(el: Knoten): boolean {
  if (!['input', 'select', 'textarea'].includes(tagName(el))) return false
  const typ = (attribut(el, 'type')?.value as Knoten | undefined)?.value
  return !(typeof typ === 'string' && KEIN_TEXTFELD.has(typ))
}

function hatText(kinder: Knoten[]): boolean {
  return kinder.some(
    (k) =>
      (k.type === 'JSXText' && (k.value as string).trim() !== '') ||
      (k.type === 'JSXExpressionContainer' &&
        (k.expression as Knoten).type !== 'JSXEmptyExpression' &&
        !(
          (k.expression as Knoten).type === 'Literal' &&
          !String((k.expression as Knoten).value).trim()
        )),
  )
}

function beschriftungenOhneFeldklasse(): string[] {
  const eigene = eigeneLabelRegeln()
  const funde: string[] = []
  for (const [datei, quelle] of Object.entries(seiten)) {
    if (EIGENE_REGEL.test(datei)) continue
    const ast = parseAst(quelle, { lang: 'tsx' }, datei) as unknown as Knoten
    const besuche = (n: unknown, vorfahren: string): void => {
      if (!n || typeof n !== 'object') return
      const k = n as Knoten
      let weiter = vorfahren
      if (k.type === 'JSXElement') {
        const kinder = k.children as Knoten[]
        if (
          tagName(k) === 'label' &&
          !attribut(k, 'className') &&
          !NEBENEINANDER.test(vorfahren) &&
          !vorfahren.split(/\s+/).some((c) => eigene.has(c)) &&
          kinder.some((c) => c.type === 'JSXElement' && istTextfeld(c)) &&
          hatText(kinder)
        )
          funde.push(
            `${datei.replace('../', 'src/')}:${quelle.slice(0, k.start as number).split('\n').length}`,
          )
        weiter = `${vorfahren} ${klassen(k)}`
      }
      for (const v of Object.values(k)) {
        if (Array.isArray(v)) v.forEach((x) => besuche(x, weiter))
        else if (v && typeof v === 'object') besuche(v, weiter)
      }
    }
    besuche(ast, '')
  }
  return funde.sort()
}

describe('Formularbeschriftung', () => {
  it('erkennt Bereiche mit eigener Regel für Beschriftungen', () => {
    expect(eigeneLabelRegeln()).toContain('assignment-dates')
  })

  it('setzt Beschriftungen von Textfeldern über das Feld (label.field mit span)', () => {
    expect(beschriftungenOhneFeldklasse()).toEqual([])
  })
})
