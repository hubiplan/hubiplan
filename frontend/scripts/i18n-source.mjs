// Statische Ergänzung zur Katalogprüfung: sichtbare Literale in bereits umgestellten
// Bereichen. Vereinsinhalte und technische Werte werden nicht automatisch übersetzt.
import { parsers } from 'prettier/plugins/typescript'

const attributes = new Set([
  'label',
  'title',
  'hint',
  'placeholder',
  'emptyText',
  'aria-label',
  'alt',
])
const properties = new Set([...attributes, 'message', 'confirmLabel', 'cancelLabel'])
const neutral = new Set(['PDF', 'CSV', 'Excel', 'HUBIplan', 'XLSX'])
const isText = (s) => typeof s === 'string' && /[a-zäöüß]/i.test(s) && !neutral.has(s.trim())

/** Kein vollständiger Datenflussnachweis; Laufzeittests bleiben für dynamische Texte nötig. */
export async function untranslatedUi(code, filename) {
  const ast = await parsers.typescript.parse(code, { filepath: filename })
  const found = []
  function report(node, text) {
    found.push({
      file: filename,
      line: node.loc.start.line,
      text: text.replace(/\s+/g, ' ').trim(),
    })
  }
  function visit(node, ancestors = []) {
    if (!node?.type) return
    if (node.type === 'CallExpression' && ['t', 'tc', 'tn'].includes(node.callee?.name)) return
    const parent = ancestors.at(-1)
    if (node.type === 'JSXText' && isText(node.value)) report(node, node.value)
    if (
      node.type === 'JSXAttribute' &&
      attributes.has(node.name.name) &&
      isText(node.value?.value)
    ) {
      report(node, node.value.value)
      return
    }
    if (node.type === 'Property' && properties.has(node.key?.name) && isText(node.value?.value)) {
      report(node, node.value.value)
      return
    }
    const expression = ancestors.findLast((n) => n.type === 'JSXExpressionContainer')
    const attribute = expression && ancestors[ancestors.indexOf(expression) - 1]
    const inDisplay =
      expression && (attribute?.type !== 'JSXAttribute' || attributes.has(attribute.name.name))
    if (
      inDisplay &&
      node.type === 'Literal' &&
      isText(node.value) &&
      ((parent?.type === 'ConditionalExpression' && parent.test !== node) ||
        (parent?.type === 'LogicalExpression' && parent.right === node))
    )
      report(node, node.value)
    if (
      inDisplay &&
      node.type === 'TemplateLiteral' &&
      node.quasis.some((q) => isText(q.value.cooked))
    ) {
      report(node, node.quasis.map((q) => q.value.cooked).join('{…}'))
      return
    }
    for (const [key, value] of Object.entries(node)) {
      if (['range', 'loc', 'tokens', 'comments'].includes(key)) continue
      if (Array.isArray(value)) value.forEach((child) => visit(child, [...ancestors, node]))
      else if (value?.type) visit(value, [...ancestors, node])
    }
  }
  visit(ast)
  return found
}

// Schrittweise abgesicherter Umfang; keine pauschale Vollständigkeitsbehauptung.
export const sourceChecked = [
  'pages/entries/EntriesPage.tsx',
  'pages/entries/UnitEntries.tsx',
  'pages/entries/CallEvent.tsx',
  'pages/entries/EntryResults.tsx',
  'components/calendar/Rsvp.tsx',
]
