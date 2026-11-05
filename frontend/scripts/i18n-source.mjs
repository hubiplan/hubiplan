// Statische Ergänzung zur Katalogprüfung in allen produktiven TS/TSX-Dateien.
// Vereinsinhalte und technische Werte werden nicht automatisch übersetzt.
import { parsers } from 'prettier/plugins/typescript'
import exceptions from './i18n-exceptions.json' with { type: 'json' }

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
// Produkt-/Markennamen, Dateiformate und unveränderte Einheiten sind keine Übersetzungen.
const neutral = new Set([
  'PDF',
  'CSV',
  'Excel',
  'HUBIplan',
  'HUBI',
  'plan',
  'XLSX',
  'JSON',
  'IBAN',
  'BIC',
  'EUR',
  'KB',
  'KB)',
  'EUR ·',
  'EUR,',
  'EUR)',
  'm',
  'mm',
  'm ·',
  'mm —',
  'SD',
  'DATEV',
  'CAMT.053',
  'Facebook',
  'Instagram',
  'YouTube',
  'TikTok',
  'X',
  'Mastodon',
  'Bluesky',
  'Threads',
  'LinkedIn',
  'Vereinsplaner',
  'instagram_basic',
  'developers.facebook.com',
])
neutral.add('i') // allgemeinverständliches Informationszeichen, mit eigenem zugänglichem Namen
const isText = (s) =>
  typeof s === 'string' &&
  /[a-zäöüß]/i.test(s) &&
  !neutral.has(s.trim()) &&
  !/^(https?:\/\/\S*|www\.\S+|\S+@\S+(?: = \S+)?)$/.test(s.trim())

/** JSX-Leerraum wie beim Rendern zusammenführen; HTML-Entitäten nicht als Wörter zählen. */
export function jsxText(raw) {
  const lines = raw.split(/\r\n|\n|\r/)
  const last = lines.findLastIndex((line) => /\S/.test(line))
  return lines
    .map((line, index) => {
      let text = line.replace(/\t/g, ' ')
      if (index) text = text.replace(/^ +/, '')
      if (index !== lines.length - 1) text = text.replace(/ +$/, '')
      return text && index < last ? `${text} ` : text
    })
    .join('')
    .replace(/&nbsp;/g, '\u00a0')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
}

/** Kein vollständiger Datenflussnachweis; Laufzeittests bleiben für dynamische Texte nötig. */
export async function untranslatedUi(code, filename) {
  const ast = await parsers.typescript.parse(code, { filepath: filename })
  const found = []
  function report(node, text) {
    if (
      exceptions.some(
        (item) => item.file === filename && item.kind === node.type && item.text === text.trim(),
      )
    )
      return
    found.push({
      file: filename,
      line: node.loc.start.line,
      text: text.replace(/\s+/g, ' ').trim(),
      start: node.range[0],
      end: node.range[1],
      kind: node.type,
    })
  }
  function visit(node, ancestors = []) {
    if (!node?.type) return
    if (node.type === 'CallExpression' && ['t', 'tc', 'tn'].includes(node.callee?.name)) {
      // Schlüssel sind angebunden; Parameter können selbst noch sichtbare Systemtexte enthalten.
      const params =
        node.arguments[node.callee.name === 't' ? 1 : node.callee.name === 'tc' ? 2 : 3]
      if (params) visit(params, [...ancestors, node])
      return
    }
    const parent = ancestors.at(-1)
    if (node.type === 'JSXText' && isText(jsxText(node.value))) report(node, jsxText(node.value))
    if (
      node.type === 'JSXAttribute' &&
      attributes.has(node.name.name) &&
      isText(node.value?.value)
    ) {
      report(node, node.value.value)
      return
    }
    const declaration = ancestors.findLast((n) => n.type === 'VariableDeclarator')
    const displayMap =
      /(?:LABELS?|Label|_WORD)$/.test(declaration?.id?.name ?? '') && parent === declaration?.init
    if (
      node.type === 'Property' &&
      (properties.has(node.key?.name) || displayMap) &&
      isText(node.value?.value)
    ) {
      report(node, node.value.value)
      return
    }
    const expression = ancestors.findLast((n) => n.type === 'JSXExpressionContainer')
    const attribute = expression && ancestors[ancestors.indexOf(expression) - 1]
    const inParams = ancestors.some(
      (n) => n.type === 'CallExpression' && ['t', 'tc', 'tn'].includes(n.callee?.name),
    )
    const inDisplay =
      inParams ||
      (expression &&
        (attribute?.type !== 'JSXAttribute' || attributes.has(attribute.name.name)) &&
        !ancestors
          .slice(ancestors.indexOf(expression) + 1)
          .some((n) => n.type === 'VariableDeclarator'))
    if (
      inDisplay &&
      node.type === 'Literal' &&
      isText(node.value) &&
      (parent?.type === 'JSXExpressionContainer' ||
        (parent?.type === 'ConditionalExpression' && parent.test !== node) ||
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

/** Endliche Schlüsselzweige in t(condition ? '…' : '…') ebenfalls katalogprüfen. */
export async function conditionalTranslationKeys(code, filename) {
  const ast = await parsers.typescript.parse(code, { filepath: filename })
  const found = []
  function alternatives(node) {
    if (node?.type === 'Literal' && typeof node.value === 'string') return [node.value]
    if (node?.type === 'ConditionalExpression') {
      const yes = alternatives(node.consequent),
        no = alternatives(node.alternate)
      return yes && no ? [...yes, ...no] : null
    }
    return null
  }
  function visit(node) {
    if (!node?.type) return
    if (
      node.type === 'CallExpression' &&
      node.callee?.name === 't' &&
      node.arguments[0]?.type === 'ConditionalExpression'
    ) {
      const keys = alternatives(node.arguments[0])
      if (keys) found.push({ line: node.loc.start.line, keys })
    }
    for (const [key, value] of Object.entries(node)) {
      if (['range', 'loc', 'tokens', 'comments'].includes(key)) continue
      if (Array.isArray(value)) value.forEach(visit)
      else if (value?.type) visit(value)
    }
  }
  visit(ast)
  return found
}

// Auf alle produktiven TS/TSX-Dateien angewendet; dynamische Server-/Vereinsinhalte
// benötigen weiterhin die separate Prüfung ihrer Herkunft und Sprachregel.
